# src/aws_resource_scheduler/utils/rds.py

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from botocore.exceptions import ClientError

class RdsModule:
    """
    Manages RDS instance start, stop, and scheduling operations.
    """

    def __init__(self, session, no_wait=False, threads=10):
        """
        Initializes the RDS module with the provided AWS session.
        """
        self.session = session
        self.client = self.session.client('rds')
        self.scheduler_summary_message = []
        self.no_wait = no_wait
        self.threads = threads

    def describe_rds_instances(self, instance_identifiers=None, tags=None, instance_attributes=None):
        paginator = self.client.get_paginator('describe_db_instances')
        page_iterator = paginator.paginate()

        rds_instances = []
        for page in page_iterator:
            for instance in page['DBInstances']:
                if instance_identifiers and instance['DBInstanceIdentifier'] not in instance_identifiers:
                    continue
                if tags:
                    try:
                        response = self.client.list_tags_for_resource(ResourceName=instance['DBInstanceArn'])
                        tags_dict = {tag['Key']: tag['Value'] for tag in response.get('TagList', [])}
                        if not all(tags_dict.get(k) == v for k, v in tags.items()):
                            continue
                    except ClientError as e:
                        logging.error(f"Failed to list tags for RDS instance {instance['DBInstanceIdentifier']}: {str(e)}")
                        continue

                instance_data = {'DBInstanceIdentifier': instance['DBInstanceIdentifier']}
                if instance_attributes:
                    for attribute in instance_attributes:
                        if attribute == 'Endpoint':
                            instance_data['Endpoint'] = instance.get('Endpoint', {}).get('Address')
                        else:
                            instance_data[attribute] = instance.get(attribute)
                rds_instances.append(instance_data)

        return rds_instances

    def wait_status(self, instance_identifier, expected_status):
        """
        Waits until the RDS instance reaches the expected status.
        """
        while True:
            status = self.instance_status(instance_identifier)
            if status == expected_status:
                return
            time.sleep(15)

    def start_instance(self, instance_identifier):
        """
        Starts the specified RDS instance if not already started.
        """
        try:
            current_status = self.instance_status(instance_identifier)
            if current_status in ["available", "starting"]:
                self.scheduler_summary_message.append(f"{instance_identifier} is already Available or Starting.")
                return
            self.client.start_db_instance(DBInstanceIdentifier=instance_identifier)
            if not self.no_wait:
                self.wait_status(instance_identifier, "available")
                self.scheduler_summary_message.append(f"{instance_identifier} started successfully.")
            else:
                self.scheduler_summary_message.append(f"{instance_identifier} start initiated (no-wait mode).")
        except ClientError as e:
            logging.error(f"Failed to start RDS instance {instance_identifier}: {str(e)}")
            self.scheduler_summary_message.append(f"Error starting {instance_identifier}: {str(e)}")

    def stop_instance(self, instance_identifier):
        """
        Stops the specified RDS instance if not already stopped.
        """
        try:
            current_status = self.instance_status(instance_identifier)
            if current_status in ["stopped", "stopping"]:
                self.scheduler_summary_message.append(f"{instance_identifier} is already in Stopping or Stopped state.")
                return
            self.client.stop_db_instance(DBInstanceIdentifier=instance_identifier)
            if not self.no_wait:
                self.wait_status(instance_identifier, "stopped")
                self.scheduler_summary_message.append(f"{instance_identifier} stopped successfully.")
            else:
                self.scheduler_summary_message.append(f"{instance_identifier} stop initiated (no-wait mode).")
        except ClientError as e:
            logging.error(f"Failed to stop RDS instance {instance_identifier}: {str(e)}")
            self.scheduler_summary_message.append(f"Error stopping {instance_identifier}: {str(e)}")

    def instance_status(self, instance_identifier):
        try:
            response = self.client.describe_db_instances(
                DBInstanceIdentifier=instance_identifier
            )
            return response['DBInstances'][0]['DBInstanceStatus']
        except ClientError as e:
            logging.error(f"Failed to get status for RDS instance {instance_identifier}: {str(e)}")
            return "unknown"

    def schedule_rds(self, data, action, instance_attributes=None):
        rds_instances = []

        if 'name' in data:
            identifiers = data['name'] if isinstance(data['name'], list) else [data['name']]
            rds_instances.extend(self.describe_rds_instances(instance_identifiers=identifiers, instance_attributes=instance_attributes))

        if 'tags' in data:
            rds_instances.extend(self.describe_rds_instances(tags=data['tags'], instance_attributes=instance_attributes))

        unique_instances = {instance['DBInstanceIdentifier']: instance for instance in rds_instances}

        if action == 'status':
            return list(unique_instances.values())

        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            if action == "stop":
                executor.map(self.stop_instance, unique_instances.keys())
            elif action == "start":
                executor.map(self.start_instance, unique_instances.keys())

        # Collect instance details for summary
        instance_details = []
        for instance_id in unique_instances.keys():
            status = self.instance_status(instance_id)
            instance_info = {
                'DBInstanceIdentifier': instance_id,
                'action': action,
                'Status': status
            }
            instance_details.append(instance_info)

        return instance_details
