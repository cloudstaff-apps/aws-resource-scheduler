# -*- coding: utf-8 -*-
import logging
import time
from concurrent.futures import ThreadPoolExecutor

class AsgModule:
    """
    Manages Auto Scaling Groups (ASG) actions such as start, stop, and status operations.
    """

    def __init__(self, session, storage, workspace_name, no_wait=False, threads=10):
        self.session = session
        self.client = self.session.client('autoscaling')
        self.storage = storage
        self.scheduler_summary_message = []
        self.workspace_name = workspace_name
        self.no_wait = no_wait
        self.threads = threads

    def get_asg_by_name(self, asg_name):
        """
        Retrieves ASG details by name.
        """
        try:
            response = self.client.describe_auto_scaling_groups(
                AutoScalingGroupNames=[asg_name]
            )
            asg = response['AutoScalingGroups'][0]
            data = {
                "asg_name": asg_name,
                "min_size": asg['MinSize'],
                "max_size": asg['MaxSize'],
                "desired_capacity": asg['DesiredCapacity'],
                "instance_count": len(asg['Instances']),
                "status": asg['Status'] if 'Status' in asg else 'InService',
            }
            return {"success": True, "data": data}
        except Exception as e:
            logging.error(f"Failed to get ASG by name: {e}")
            return {"success": False, "data": f"Scheduler failed for: {asg_name}. Please check it."}

    def get_asg_by_tags(self, tags):
        """
        Retrieves a list of ASGs that match the given tags.
        """
        paginator = self.client.get_paginator('describe_auto_scaling_groups')
        asg_list = []

        for page in paginator.paginate():
            for asg in page['AutoScalingGroups']:
                asg_tags = {tag['Key']: tag['Value'] for tag in asg.get('Tags', [])}
                if all(asg_tags.get(k) == v for k, v in tags.items()):
                    asg_list.append(asg['AutoScalingGroupName'])
        return asg_list

    def main_scheduler_asg(self, data, action):
        """
        Main function to handle ASG actions (start, stop, status).
        """
        name_asg_list = data.get('name', [])
        tag_asg_list = []

        if 'tags' in data:
            tag_asg_list = self.get_asg_by_tags(data['tags'])

        final_asg_list = list(set(name_asg_list + tag_asg_list))
        asg_data_list = []

        for asg in final_asg_list:
            resp = self.get_asg_by_name(asg)
            if resp['success']:
                asg_data_list.append(resp['data'])

        # Return the length based on actual unique ASG data
        if action == 'status':
            return asg_data_list

        self.update_asg(asg_data_list, action)
        return self.scheduler_summary_message

    def update_asg(self, asg_details_list, action):
        """
        Updates the ASGs based on the action (start, stop).
        """
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            if action == "start":
                executor.map(self.start_asg, asg_details_list)
            elif action == "stop":
                executor.map(self.stop_asg, asg_details_list)

    def start_asg(self, asg_data):
        asg_name = asg_data['asg_name']

        # Check current ASG state before starting
        if asg_data['desired_capacity'] > 0:
            logging.info(f"ASG {asg_name} is already running with desired capacity: {asg_data['desired_capacity']}.")
            self.scheduler_summary_message.append(f"ASG {asg_name} is already in a running state.")
            return

        # Read desired capacity, min_size, max_size from storage
        parameter_name = f"/scheduler/{self.workspace_name}/asg/{asg_name}"
        value = self.storage.read_state(parameter_name)

        if value and len(value) == 4:
            _, desired_capacity, min_size, max_size = value
            desired_capacity = int(desired_capacity)
            min_size = int(min_size)
            max_size = int(max_size)
        else:
            logging.error(f"No stored data found for ASG {asg_name}. Cannot start.")
            self.scheduler_summary_message.append(f"ASG {asg_name} cannot be started due to missing stored data.")
            return

        # Update the ASG to the desired settings
        self.client.update_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            MinSize=min_size,
            MaxSize=max_size,
            DesiredCapacity=desired_capacity
        )
        if not self.no_wait:
            self.check_instance_start_status(asg_data)
        else:
            self.scheduler_summary_message.append(f"ASG {asg_name} start initiated (no-wait mode).")

    def stop_asg(self, asg_data):
        asg_name = asg_data['asg_name']

        # Check current ASG state before stopping
        if asg_data['desired_capacity'] == 0:
            logging.info(f"ASG {asg_name} is already stopped with desired capacity: 0.")
            self.scheduler_summary_message.append(f"ASG {asg_name} is already in a stopped state.")
            return

        # Store current desired capacity, min_size, max_size to storage
        parameter_name = f"/scheduler/{self.workspace_name}/asg/{asg_name}"
        desired_capacity = str(asg_data['desired_capacity'])
        min_size = str(asg_data['min_size'])
        max_size = str(asg_data['max_size'])
        value = [asg_name, desired_capacity, min_size, max_size]
        self.storage.write_state(parameter_name, value)

        # Update the ASG to zero to stop it
        self.client.update_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            MinSize=0, MaxSize=0, DesiredCapacity=0
        )
        if not self.no_wait:
            self.check_instance_stop_status(asg_data)
        else:
            self.scheduler_summary_message.append(f"ASG {asg_name} stop initiated (no-wait mode).")

    def check_instance_start_status(self, asg_data):
        """
        Check the start status of instances in the ASG.
        """
        asg_name = asg_data['asg_name']
        desired_count = asg_data['desired_capacity']
        instance_count = 0

        while instance_count < desired_count:
            instance_list = self.get_asg_instance_health(asg_name)
            instance_count = sum(1 for instance in instance_list if instance['LifecycleState'] == "InService")
            time.sleep(10)

        self.scheduler_summary_message.append(f"ASG {asg_name} is fully started!")

    def check_instance_stop_status(self, asg_data):
        """
        Check the stop status of instances in the ASG.
        """
        asg_name = asg_data['asg_name']
        while True:
            response = self.client.describe_auto_scaling_groups(
                AutoScalingGroupNames=[asg_name]
            )
            instances = response['AutoScalingGroups'][0]['Instances']
            if not instances:
                break
            time.sleep(10)
        self.scheduler_summary_message.append(f"ASG {asg_name} is fully stopped!")

    def get_asg_instance_health(self, asg_name):
        """
        Retrieves the health status of instances in the ASG.
        """
        response = self.client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[asg_name]
        )
        asg = response['AutoScalingGroups'][0]
        return asg.get('Instances', [])
