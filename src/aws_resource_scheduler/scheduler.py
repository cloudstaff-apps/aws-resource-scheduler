# -*- coding: utf-8 -*-

import logging
from datetime import datetime
from aws_resource_scheduler.utils.asg import AsgModule
from aws_resource_scheduler.utils.rds import RdsModule
from aws_resource_scheduler.utils.ec2 import Ec2Module
from aws_resource_scheduler.utils.aurora import AuroraModule
from aws_resource_scheduler.utils.ecs import EcsModule
from aws_resource_scheduler.utils.common import parse_arguments, evaluate, aws_login, send_chat_notification, Storage, ParameterStoreStorage, DynamoDBStorage

def main(args=None):
    """
    Main function to parse arguments, evaluate configuration, and perform actions
    on AWS resources such as EC2, ASG, RDS, Aurora, and ECS. Also sends notifications
    to the specified chat platform (Google Chat, Slack, Teams) if enabled.
    """
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    if args is None:
        # Parse command-line arguments and fetch configuration
        args = parse_arguments()

    workspace, resources, action, workspace_name, no_wait, threads = evaluate(args)

    # Determine storage method
    storage_config = workspace.get('storage', {})
    storage_method = storage_config.get('method', 'parameter_store')
    if storage_method == 'dynamodb':
        table_name = storage_config.get('dynamodb_table')
        if not table_name:
            logging.error("DynamoDB table name not specified in configuration.")
            exit(1)
        
    # Initialize response containers for different AWS resources
    rds_scheduler_resp = []
    asg_scheduler_resp = []
    ec2_scheduler_resp = []
    aurora_scheduler_resp = []
    ecs_scheduler_resp = []

    # Check if 'notification' block exists and then handle the notification logic
    notification_settings = workspace.get("notification", {})
    notification_enabled = notification_settings.get("enable", False)
    platform = notification_settings.get("platform", "google")  # Default to Google Chat
    webhook_url = notification_settings.get("webhook_url")

    try:
        client = aws_login(workspace)
        # Initialize storage handler
        if storage_method == 'dynamodb':
            storage = DynamoDBStorage(session=client, table_name=table_name)
        else:
            storage = ParameterStoreStorage(session=client)
        for res in resources:
            logging.info(f"Process started for {res} at: {datetime.now()}")

            try:
                if res == "rds" and res in workspace:
                    rds_module = RdsModule(session=client, no_wait=no_wait, threads=threads)
                    attributes = ['DBInstanceIdentifier', 'DBInstanceStatus', 'DBInstanceClass', 'Engine', 'Endpoint']
                    rds_scheduler_resp = rds_module.schedule_rds(workspace[res], action, instance_attributes=attributes)

                elif res == "asg" and res in workspace:
                    asg_module = AsgModule(session=client, storage=storage, workspace_name=workspace_name, no_wait=no_wait, threads=threads)
                    asg_scheduler_resp = asg_module.main_scheduler_asg(workspace[res], action)

                elif res == "ec2" and res in workspace:
                    ec2_module = Ec2Module(session=client, no_wait=no_wait, threads=threads)
                    attributes = ['InstanceId', 'InstanceType', 'State', 'PrivateIpAddress', 'PublicIpAddress']
                    ec2_scheduler_resp = ec2_module.schedule_ec2_instances(workspace[res], action, instance_attributes=attributes)

                elif res == "aurora" and res in workspace:
                    aurora_module = AuroraModule(session=client, no_wait=no_wait, threads=threads)
                    cluster_attributes = ['DBClusterIdentifier', 'Status', 'Engine', 'Endpoint']
                    aurora_scheduler_resp = aurora_module.schedule_aurora(workspace[res], action, cluster_attributes=cluster_attributes)

                elif res == "ecs" and res in workspace:
                    ecs_module = EcsModule(session=client, storage=storage, workspace_name=workspace_name, no_wait=no_wait, threads=threads)
                    ecs_scheduler_resp = ecs_module.main_scheduler_ecs(workspace[res], action)

                else:
                    logging.warning(f"Resource '{res}' is not supported or not configured in the workspace.")

                logging.info(f"Process ended for {res} at: {datetime.now()}")

            except Exception as e:
                logging.exception(f"An error occurred while processing resource {res}: {e}")
                if notification_enabled and webhook_url:
                    send_chat_notification(platform, webhook_url, f"An error occurred while processing resource {res}: {e}")

    except Exception as e:
        logging.exception(f"An error occurred during AWS session setup or overall execution: {e}")
        if notification_enabled and webhook_url:
            send_chat_notification(platform, webhook_url, f"An error occurred during AWS session setup or overall execution: {e}")
        return

    # Prepare the summary of actions performed on each AWS resource
    data_lines = []

    if rds_scheduler_resp:
        data_lines.append(f"--------Details about RDS Total: {len(rds_scheduler_resp)} -------")
        for instance in rds_scheduler_resp:
            line = ", ".join(f"{key}: {value}" for key, value in instance.items())
            data_lines.append(line)

    if asg_scheduler_resp:
        data_lines.append(f"--------Details about ASG Total: {len(asg_scheduler_resp)} -------")
        if action == 'status':
            for asg in asg_scheduler_resp:
                line = ", ".join(f"{key}: {value}" for key, value in asg.items())
                data_lines.append(line)
        else:
            data_lines.extend(asg_scheduler_resp)

    if ec2_scheduler_resp:
        data_lines.append(f"--------Details about EC2 Total: {len(ec2_scheduler_resp)} -------")
        for instance in ec2_scheduler_resp:
            line = ", ".join(f"{key}: {value}" for key, value in instance.items())
            data_lines.append(line)

    if aurora_scheduler_resp:
        data_lines.append(f"--------Details about Aurora Total: {len(aurora_scheduler_resp)} -------")
        for instance in aurora_scheduler_resp:
            line = ", ".join(f"{key}: {value}" for key, value in instance.items())
            data_lines.append(line)

    if ecs_scheduler_resp:
        data_lines.append(f"--------Details about ECS Total: {len(ecs_scheduler_resp)} -------")
        if action == 'status':
            for service in ecs_scheduler_resp:
                line = ", ".join(f"{key}: {value}" for key, value in service.items())
                data_lines.append(line)
        else:
            data_lines.extend(ecs_scheduler_resp)

    summary = "\n".join(data_lines)
    logging.info(summary)

    # Send the summary as a chat notification if enabled
    if notification_enabled and webhook_url:
        send_chat_notification(platform, webhook_url, summary)


if __name__ == '__main__':
    main()
