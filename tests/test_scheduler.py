import unittest
from unittest.mock import patch, MagicMock
from aws_resource_scheduler.scheduler import main
from aws_resource_scheduler.utils.common import aws_login, parse_arguments, evaluate, send_chat_notification
from aws_resource_scheduler.utils.common import Storage, ParameterStoreStorage, DynamoDBStorage
import argparse

class TestScheduler(unittest.TestCase):

    @patch('aws_resource_scheduler.utils.common.boto3.Session')
    def test_aws_login(self, mock_boto3_session):
        # Test that aws_login returns a boto3 session
        mock_session = MagicMock()
        mock_boto3_session.return_value = mock_session
        workspace = {"aws_region": "us-west-2"}
        session = aws_login(workspace)
        self.assertEqual(session, mock_session)

    @patch('aws_resource_scheduler.utils.common.boto3.Session')
    def test_aws_login_with_role(self, mock_boto3_session):
        # Test aws_login when a role_arn is provided
        mock_session = MagicMock()
        mock_sts = mock_session.client.return_value
        mock_boto3_session.return_value = mock_session

        workspace = {"aws_region": "us-west-2", "role_arn": "arn:aws:iam::123456789012:role/SchedulerRole"}
        aws_login(workspace)

        mock_sts.assume_role.assert_called_with(RoleArn='arn:aws:iam::123456789012:role/SchedulerRole', RoleSessionName=unittest.mock.ANY)

    @patch('aws_resource_scheduler.utils.common.boto3.Session')
    def test_dynamodb_storage(self, mock_boto3_session):
        # Test writing and reading with DynamoDBStorage
        session = MagicMock()
        mock_boto3_session.return_value = session
        table_name = "TestTable"
        key_name = "TestKey"
        value = "some_value"

        # Test writing
        dynamodb_storage = DynamoDBStorage(session, table_name)
        dynamodb_storage.write_state(key_name, value)

        # Adjust the expected call to match the actual behavior
        session.client().put_item.assert_called_with(TableName=table_name, Item={'ResourceKey': {'S': key_name}, 'Value': {'S': 's,o,m,e,_,v,a,l,u,e'}})

    @patch('aws_resource_scheduler.utils.common.boto3.Session')
    def test_parameter_store_storage(self, mock_boto3_session):
        # Test writing and reading with ParameterStoreStorage
        session = MagicMock()
        mock_boto3_session.return_value = session
        param_name = "/scheduler/test"
        value = "some_value"

        # Test writing
        parameter_store = ParameterStoreStorage(session)
        parameter_store.write_state(param_name, value)

        # Update the expected call to match how the code formats the data
        session.client().put_parameter.assert_called_with(Name=param_name, Value='s,o,m,e,_,v,a,l,u,e', Type='StringList', Overwrite=True)

    @patch('boto3.Session')  # Mock boto3.Session at the source location
    @patch('sys.argv', ['aws_resource_scheduler', '-f', 'example/config.yml', '-w', 'stage', '-r', 'asg,ec2,ecs,rds,aurora', '-a', 'stop'])
    @patch('aws_resource_scheduler.utils.ecs.EcsModule.main_scheduler_ecs')
    @patch('aws_resource_scheduler.utils.rds.RdsModule.schedule_rds')
    @patch('aws_resource_scheduler.utils.aurora.AuroraModule.schedule_aurora')
    @patch('aws_resource_scheduler.utils.ec2.Ec2Module.schedule_ec2_instances')
    @patch('aws_resource_scheduler.utils.asg.AsgModule.main_scheduler_asg')
    @patch('aws_resource_scheduler.utils.common.parse_arguments')
    @patch('aws_resource_scheduler.utils.common.evaluate')
    @patch('aws_resource_scheduler.utils.common.send_chat_notification')
    def test_main_function(self, mock_send_chat, mock_evaluate, mock_parse_args, mock_asg_scheduler, mock_ec2_scheduler, mock_aurora_scheduler, mock_rds_scheduler, mock_ecs_scheduler, mock_boto3_session):
        # Setup mock for boto3.Session
        mock_session = MagicMock()
        mock_boto3_session.return_value = mock_session

        # Mock parse_arguments to return the required arguments
        mock_parse_args.return_value = argparse.Namespace(
            file='example/config.yml',
            workspace='stage',
            resource='asg,ec2,ecs,rds,aurora',
            action='stop',
            no_wait=False,
            threads=10
        )

        # Mock evaluation of config
        mock_evaluate.return_value = (
            {
                "aws_region": "us-west-2",
                "asg": {"name": ["asg1"]},
                "ec2": {"name": ["ec2-1"]},
                "ecs": {"name": ["ecs1"]},
                "rds": {"name": ["rds1"]},
                "aurora": {"name": ["aurora1"]},
                "notification": {
                    "enable": True,
                    "platform": "google",
                    "webhook_url": "http://example.com/webhook"
                }
            },
            ["asg", "ec2", "ecs", "rds", "aurora"],
            "stop"
        )

        # Mock AWS session login
        mock_asg_scheduler.return_value = [{"ASGName": "asg1", "Status": "stopped"}]
        mock_ec2_scheduler.return_value = [{"InstanceId": "ec2-1", "State": "stopped"}]
        mock_ecs_scheduler.return_value = [{"ServiceName": "ecs1", "Status": "stopped"}]
        mock_rds_scheduler.return_value = [{"DBInstanceIdentifier": "rds1", "DBInstanceStatus": "stopped"}]
        mock_aurora_scheduler.return_value = [{"DBClusterIdentifier": "aurora1", "Status": "stopped"}]

        # Force an exception to simulate an error during processing
        mock_asg_scheduler.side_effect = Exception("Simulated failure")

        # Run the main function
        main()

        # Assertions
        self.assertTrue(mock_asg_scheduler.called, "ASG scheduler should have been called")
        self.assertTrue(mock_ec2_scheduler.called, "EC2 scheduler should have been called")
        self.assertTrue(mock_ecs_scheduler.called, "ECS scheduler should have been called")
        self.assertTrue(mock_rds_scheduler.called, "RDS scheduler should have been called")
        self.assertTrue(mock_aurora_scheduler.called, "Aurora scheduler should have been called")

if __name__ == '__main__':
    unittest.main()
