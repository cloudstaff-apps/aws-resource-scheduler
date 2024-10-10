# -*- coding: utf-8 -*-
import yaml
import argparse
import boto3
import random
import requests
import logging
from botocore.exceptions import ClientError

def get_config(file):
    """
    Reads and returns the content of the YAML configuration file.
    """
    try:
        with open(file, 'r') as f:
            config = yaml.safe_load(f)
            return config
    except Exception as e:
        logging.error(f"Unable to open the YAML config file {file}. Error: {str(e)}")
        return None

def parse_arguments():
    """
    Parses command-line arguments for the script.
    """
    parser = argparse.ArgumentParser(description="AWS Resource Scheduler")
    parser.add_argument("-f", "--filename", dest="file", help="Name of config file", required=True)
    parser.add_argument("-w", "--workspace", dest="workspace", help="Workspace name", required=True)
    parser.add_argument("-r", "--resource", dest="resource", help="Comma-separated AWS resources (e.g., rds, ec2, asg)", required=True)
    parser.add_argument("-a", "--action", dest="action", choices=['start', 'stop', 'status'], help="Action to perform", required=True)
    parser.add_argument("-n", "--no-wait", dest="no_wait", action='store_true', help="Do not wait for resources to reach desired state after starting or stopping")
    parser.add_argument("-t", "--threads", dest="threads", type=int, default=10, help="Number of threads to use for parallel operations (default: 10)")

    args = parser.parse_args()
    logging.info(f"Config Filename: {args.file}, Workspace: {args.workspace}, Resource list: {args.resource.split(',')}, Action: {args.action}, No Wait: {args.no_wait}, Threads: {args.threads}")
    return args

def evaluate(args):
    """
    Processes the parsed arguments and retrieves the workspace configuration from the YAML file.
    """
    environment = args.workspace
    resources = args.resource.split(',')
    action = args.action
    config_yaml = args.file
    no_wait = args.no_wait
    threads = args.threads

    config = get_config(config_yaml)
    if not config:
        logging.error("Configuration could not be loaded.")
        exit(1)

    config_workspace = config.get('workspaces', {}).get(environment)
    if not config_workspace:
        logging.error(f"Workspace '{environment}' not found in the configuration file.")
        exit(1)

    return config_workspace, resources, action, args.workspace, no_wait, threads

def aws_login(workspace):
    """
    Creates an AWS session using the provided workspace configuration.
    """
    region = workspace.get("aws_region")
    session = boto3.Session(region_name=region)

    if "role_arn" in workspace:
        sts = session.client("sts")
        role = workspace["role_arn"]
        try:
            response = sts.assume_role(RoleArn=role, RoleSessionName=f"scheduler_{random.randint(1, 999)}")
            session = boto3.Session(
                aws_access_key_id=response['Credentials']['AccessKeyId'],
                aws_secret_access_key=response['Credentials']['SecretAccessKey'],
                aws_session_token=response['Credentials']['SessionToken'],
                region_name=region
            )
        except Exception as e:
            logging.error(f"Failed to assume role: {str(e)}")
            exit(1)
    return session

def send_chat_notification(platform, webhook_url, message):
    """
    Sends a notification to the specified platform (Slack, Google Chat, Teams) using a webhook.
    """
    if platform == "teams":
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "text": message
        }
    else:
        payload = {"text": message}

    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(webhook_url, json=payload, headers=headers)
        if response.status_code == 200:
            logging.info(f"{platform.capitalize()} notification sent successfully.")
            return True
        else:
            logging.error(f"Failed to send {platform.capitalize()} notification. Status code: {response.status_code}")
            return False
    except Exception as e:
        logging.error(f"An error occurred while sending the {platform.capitalize()} notification: {str(e)}")
        return False

# Storage classes
class Storage:
    def read_state(self, key):
        raise NotImplementedError

    def write_state(self, key, value):
        raise NotImplementedError

class ParameterStoreStorage(Storage):
    def __init__(self, session):
        self.client = session.client('ssm')

    def read_state(self, key):
        try:
            response = self.client.get_parameter(Name=key)
            value = response['Parameter']['Value'].split(',')
            logging.info(f"Parameter {key} read from Parameter Store.")
            return value
        except self.client.exceptions.ParameterNotFound:
            logging.info(f"Parameter {key} not found.")
            return []
        except ClientError as e:
            logging.error(f"Failed to read parameter {key}: {str(e)}")
            return []

    def write_state(self, key, value):
        try:
            self.client.put_parameter(
                Name=key,
                Value=",".join(value),
                Type="StringList",
                Overwrite=True
            )
            logging.info(f"Parameter {key} updated in Parameter Store.")
        except ClientError as e:
            logging.error(f"Failed to write parameter {key}: {str(e)}")

class DynamoDBStorage(Storage):
    def __init__(self, session, table_name):
        self.client = session.client('dynamodb')
        self.table_name = table_name

    def read_state(self, key):
        try:
            response = self.client.get_item(
                TableName=self.table_name,
                Key={'ResourceKey': {'S': key}}
            )
            if 'Item' in response:
                value = response['Item']['Value']['S'].split(',')
                logging.info(f"Item {key} read from DynamoDB table {self.table_name}.")
                return value
            else:
                logging.info(f"Item {key} not found in DynamoDB table {self.table_name}.")
                return []
        except ClientError as e:
            logging.error(f"Failed to read item {key} from DynamoDB: {str(e)}")
            return []

    def write_state(self, key, value):
        try:
            self.client.put_item(
                TableName=self.table_name,
                Item={
                    'ResourceKey': {'S': key},
                    'Value': {'S': ",".join(value)}
                }
            )
            logging.info(f"Item {key} updated in DynamoDB table {self.table_name}.")
        except ClientError as e:
            logging.error(f"Failed to write item {key} to DynamoDB: {str(e)}")
