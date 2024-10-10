# src/aws_resource_scheduler/utils/ec2.py

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from botocore.exceptions import ClientError

class Ec2Module:
    """
    Manages EC2 instances' start, stop, and scheduling operations.
    """

    def __init__(self, session, no_wait=False, threads=10):
        """
        Initializes the EC2 module with the provided AWS session.
        """
        self.session = session
        self.client = self.session.client('ec2')
        self.scheduler_summary_message = []
        self.no_wait = no_wait
        self.threads = threads

    def describe_ec2_instances(self, instance_ids=None, tags=None, instance_attributes=None):
        """
        Describes EC2 instances based on instance IDs or tags.
        """
        filters = []
        if tags:
            filters.extend([{'Name': f'tag:{k}', 'Values': [v]} for k, v in tags.items()])

        try:
            response = self.client.describe_instances(
                InstanceIds=instance_ids or [],
                Filters=filters
            )
        except ClientError as e:
            logging.error(f"Failed to describe EC2 instances: {str(e)}")
            return []

        ec2_instances = []
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                instance_data = {'InstanceId': instance['InstanceId']}
                if instance_attributes:
                    for attribute in instance_attributes:
                        if attribute == 'State':
                            instance_data['State'] = instance['State']['Name']
                        else:
                            instance_data[attribute] = instance.get(attribute)
                ec2_instances.append(instance_data)

        return ec2_instances

    def wait_status(self, instance_id, expected_status):
        """
        Wait until the EC2 instance reaches the desired status.
        """
        while True:
            status = self.instance_status(instance_id)
            if status == expected_status:
                return
            time.sleep(15)

    def start_instance(self, instance_id):
        """
        Start the specified EC2 instance if not already running.
        """
        try:
            current_status = self.instance_status(instance_id)
            if current_status in ["running", "pending"]:
                self.scheduler_summary_message.append(f"{instance_id} is already Running or Starting.")
                return
            self.client.start_instances(InstanceIds=[instance_id])
            if not self.no_wait:
                self.wait_status(instance_id, "running")
                self.scheduler_summary_message.append(f"{instance_id} started successfully.")
            else:
                self.scheduler_summary_message.append(f"{instance_id} start initiated (no-wait mode).")
        except ClientError as e:
            logging.error(f"Failed to start EC2 instance {instance_id}: {str(e)}")
            self.scheduler_summary_message.append(f"Error starting {instance_id}: {str(e)}")

    def stop_instance(self, instance_id):
        """
        Stop the specified EC2 instance if not already stopped.
        """
        try:
            current_status = self.instance_status(instance_id)
            if current_status in ["stopped", "stopping"]:
                self.scheduler_summary_message.append(f"{instance_id} is already in Stopping or Stopped state.")
                return
            self.client.stop_instances(InstanceIds=[instance_id])
            if not self.no_wait:
                self.wait_status(instance_id, "stopped")
                self.scheduler_summary_message.append(f"{instance_id} stopped successfully.")
            else:
                self.scheduler_summary_message.append(f"{instance_id} stop initiated (no-wait mode).")
        except ClientError as e:
            logging.error(f"Failed to stop EC2 instance {instance_id}: {str(e)}")
            self.scheduler_summary_message.append(f"Error stopping {instance_id}: {str(e)}")

    def instance_status(self, instance_id):
        """
        Check the current status of the instance.
        """
        try:
            response = self.client.describe_instances(InstanceIds=[instance_id])
            return response['Reservations'][0]['Instances'][0]['State']['Name']
        except ClientError as e:
            logging.error(f"Failed to get status for EC2 instance {instance_id}: {str(e)}")
            return "unknown"

    def schedule_ec2_instances(self, data, action, instance_attributes=None):
        """
        Main EC2 scheduler function to handle instance start/stop/status based on the configuration.
        """
        ec2_instances = []

        if 'name' in data:
            instance_ids = data['name'] if isinstance(data['name'], list) else [data['name']]
            ec2_instances.extend(self.describe_ec2_instances(instance_ids=instance_ids, instance_attributes=instance_attributes))

        if 'tags' in data:
            ec2_instances.extend(self.describe_ec2_instances(tags=data['tags'], instance_attributes=instance_attributes))

        unique_instances = {instance['InstanceId']: instance for instance in ec2_instances}

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
                'InstanceId': instance_id,
                'action': action,
                'Status': status
            }
            instance_details.append(instance_info)

        return instance_details
