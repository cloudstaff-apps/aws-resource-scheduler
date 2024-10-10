import logging
import time
from concurrent.futures import ThreadPoolExecutor

class EcsModule:
    def __init__(self, session, storage, workspace_name, no_wait=False, threads=10):
        self.session = session
        self.client = self.session.client('ecs')
        self.application_autoscaling_client = self.session.client('application-autoscaling')
        self.storage = storage
        self.scheduler_summary_message = []
        self.workspace_name = workspace_name
        self.no_wait = no_wait
        self.threads = threads

    def get_services_by_tags(self, cluster_name, tags):
        paginator = self.client.get_paginator('list_services')
        service_arns = []
        for page in paginator.paginate(cluster=cluster_name):
            service_arns.extend(page['serviceArns'])

        services = []
        for i in range(0, len(service_arns), 10):
            batch_arns = service_arns[i:i + 10]
            response = self.client.describe_services(cluster=cluster_name, services=batch_arns)
            for service in response['services']:
                response_tags = self.client.list_tags_for_resource(resourceArn=service['serviceArn'])
                service_tags = {tag['key']: tag['value'] for tag in response_tags.get('tags', [])}
                if all(service_tags.get(k) == v for k, v in tags.items()):
                    services.append(service['serviceName'])
        return services

    def get_ecs_service_status(self, cluster_name, service_name):
        response = self.client.describe_services(cluster=cluster_name, services=[service_name])
        service_data = response['services'][0]
        return {
            "cluster_name": cluster_name,
            "service_name": service_name,
            "desired_count": service_data['desiredCount'],
            "running_count": service_data['runningCount'],
            "status": service_data['status'],
            "launch_type": service_data.get('launchType', 'UNKNOWN'),
            "task_definition": service_data['taskDefinition'],
        }

    def main_scheduler_ecs(self, ecs_config, action):
        service_data_list = []

        for cluster_name, config in ecs_config.items():
            services = config.get('services', [])
            tags = config.get('tags', {})

            # Add services specified by name
            for service_name in services:
                service_data = self.get_ecs_service_status(cluster_name, service_name)
                service_data_list.append(service_data)

            # Add services discovered via tags
            if tags:
                tagged_services = self.get_services_by_tags(cluster_name, tags)
                for service_name in tagged_services:
                    service_data = self.get_ecs_service_status(cluster_name, service_name)
                    service_data_list.append(service_data)

        if action == 'status':
            return service_data_list

        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            if action == "start":
                executor.map(self.safe_execution, [self.start_ecs_service] * len(service_data_list), service_data_list)
            elif action == "stop":
                executor.map(self.safe_execution, [self.stop_ecs_service] * len(service_data_list), service_data_list)

        return self.scheduler_summary_message

    def safe_execution(self, func, service_data):
        try:
            func(service_data)
        except Exception as e:
            service_name = service_data.get('service_name', 'Unknown')
            cluster_name = service_data.get('cluster_name', 'Unknown')
            logging.error(f"An error occurred while processing service {service_name} in cluster {cluster_name}: {str(e)}")
            self.scheduler_summary_message.append(f"Failed to process service {service_name} in cluster {cluster_name}.")

    def start_ecs_service(self, service_data):
        cluster_name = service_data['cluster_name']
        service_name = service_data['service_name']
        parameter_name = f"/scheduler/{self.workspace_name}/ecs/{cluster_name}/{service_name}"
        stored_data = self.storage.read_state(parameter_name)

        if not stored_data or len(stored_data) < 3:
            logging.error(f"No stored data found for ECS service {service_name} in cluster {cluster_name}. Cannot start.")
            self.scheduler_summary_message.append(f"ECS service {service_name} cannot be started due to missing stored data.")
            return

        desired_count = int(stored_data[2])
        min_capacity = int(stored_data[3]) if len(stored_data) > 3 else None
        max_capacity = int(stored_data[4]) if len(stored_data) > 4 else None

        current_status = self.get_ecs_service_status(cluster_name, service_name)
        if current_status['running_count'] == desired_count:
            logging.info(f"Service {service_name} in cluster {cluster_name} is already at desired count.")
            self.scheduler_summary_message.append(f"Service {service_name} in cluster {cluster_name} is already at desired count.")
            return

        if min_capacity is not None and max_capacity is not None:
            self.update_scaling_policy(cluster_name, service_name, min_capacity, max_capacity)

        self.update_ecs_service(cluster_name, service_name, desired_count)
        if not self.no_wait:
            self.wait_for_service(cluster_name, service_name, desired_count)
            self.scheduler_summary_message.append(f"Service {service_name} in cluster {cluster_name} started successfully.")
        else:
            self.scheduler_summary_message.append(f"Service {service_name} in cluster {cluster_name} start initiated (no-wait mode).")

    def stop_ecs_service(self, service_data):
        cluster_name = service_data['cluster_name']
        service_name = service_data['service_name']
        parameter_name = f"/scheduler/{self.workspace_name}/ecs/{cluster_name}/{service_name}"

        current_status = self.get_ecs_service_status(cluster_name, service_name)
        if current_status['running_count'] == 0:
            logging.info(f"Service {service_name} in cluster {cluster_name} is already stopped.")
            self.scheduler_summary_message.append(f"Service {service_name} in cluster {cluster_name} is already stopped.")
            return

        scaling_policy = self.describe_scaling_policy(cluster_name, service_name)

        if scaling_policy:
            stored_data = [
                str(cluster_name),
                str(service_name),
                str(current_status['desired_count']),
                str(scaling_policy['min_capacity']),
                str(scaling_policy['max_capacity'])
            ]
        else:
            stored_data = [str(cluster_name), str(service_name), str(current_status['desired_count'])]
        
        self.storage.write_state(parameter_name, stored_data)

        if scaling_policy:
            self.update_scaling_policy(cluster_name, service_name, min_capacity=0, max_capacity=0)

        self.update_ecs_service(cluster_name, service_name, 0)
        if not self.no_wait:
            self.wait_for_service(cluster_name, service_name, 0)
            self.scheduler_summary_message.append(f"Service {service_name} in cluster {cluster_name} stopped successfully.")
        else:
            self.scheduler_summary_message.append(f"Service {service_name} in cluster {cluster_name} stop initiated (no-wait mode).")

    def update_ecs_service(self, cluster_name, service_name, desired_count):
        self.client.update_service(
            cluster=cluster_name,
            service=service_name,
            desiredCount=desired_count
        )
        logging.info(f"Service {service_name} in cluster {cluster_name} updated to desired count: {desired_count}")

    def wait_for_service(self, cluster_name, service_name, expected_running_count):
        while True:
            status_data = self.get_ecs_service_status(cluster_name, service_name)
            if status_data['running_count'] == expected_running_count:
                return
            time.sleep(15)

    def describe_scaling_policy(self, cluster_name, service_name):
        response = self.application_autoscaling_client.describe_scalable_targets(
            ServiceNamespace='ecs',
            ResourceIds=[f'service/{cluster_name}/{service_name}']
        )

        if response['ScalableTargets']:
            scalable_target = response['ScalableTargets'][0]
            return {
                "min_capacity": scalable_target.get('MinCapacity', 0),
                "max_capacity": scalable_target.get('MaxCapacity', 0)
            }
        return {}

    def update_scaling_policy(self, cluster_name, service_name, min_capacity, max_capacity):
        self.application_autoscaling_client.register_scalable_target(
            ServiceNamespace='ecs',
            ResourceId=f'service/{cluster_name}/{service_name}',
            ScalableDimension='ecs:service:DesiredCount',
            MinCapacity=min_capacity,
            MaxCapacity=max_capacity
        )
        logging.info(f"Updated scaling policy for service {service_name} in cluster {cluster_name} with MinCapacity: {min_capacity}, MaxCapacity: {max_capacity}")
