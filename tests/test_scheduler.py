import unittest
from unittest.mock import patch, MagicMock
from aws_resource_scheduler.scheduler import main
from aws_resource_scheduler.utils.common import aws_login, write_to_parameter_store, read_from_parameter_store

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

        mock_sts.assume_role.assert_called_with(
            RoleArn='arn:aws:iam::123456789012:role/SchedulerRole', 
            RoleSessionName=unittest.mock.ANY
        )

    @patch('aws_resource_scheduler.utils.common.boto3.Session')
    @patch('aws_resource_scheduler.utils.common.write_to_parameter_store')
    def test_write_to_parameter_store(self, mock_write_to_ps, mock_boto3_session):
        # Test writing to parameter store
        session = MagicMock()
        mock_boto3_session.return_value = session
        param_name = "/scheduler/test"
        value = ['asg1,0,1,2', 'ecs1,1']

        write_to_parameter_store(session, param_name, value)

        mock_write_to_ps.assert_called_once_with(session, param_name, value)

    @patch('aws_resource_scheduler.utils.common.boto3.Session')
    @patch('aws_resource_scheduler.utils.common.read_from_parameter_store')
    def test_read_from_parameter_store(self, mock_read_from_ps, mock_boto3_session):
        # Test reading from parameter store
        session = MagicMock()
        mock_boto3_session.return_value = session
        param_name = "/scheduler/test"
        mock_read_from_ps.return_value = ['asg1,0,1,2', 'ecs1,1']

        result = read_from_parameter_store(session, param_name)

        mock_read_from_ps.assert_called_once_with(session, param_name)
        self.assertEqual(result, ['asg1,0,1,2', 'ecs1,1'])

    @patch('aws_resource_scheduler.utils.ec2.Ec2Module.schedule_ec2_instances')
    @patch('aws_resource_scheduler.utils.asg.AsgModule.main_scheduler_asg')
    @patch('aws_resource_scheduler.utils.rds.RdsModule.schedule_rds')
    @patch('aws_resource_scheduler.utils.ecs.EcsModule.main_scheduler_ecs')
    @patch('aws_resource_scheduler.utils.common.aws_login')
    @patch('aws_resource_scheduler.utils.common.parse_arguments')
    @patch('aws_resource_scheduler.utils.common.evaluate')
    @patch('aws_resource_scheduler.utils.common.send_chat_notification')
    def test_main_function(self, mock_send_chat, mock_evaluate, mock_parse_args, mock_aws_login, 
                           mock_ecs_scheduler, mock_rds_scheduler, mock_asg_scheduler, mock_ec2_scheduler):
        # Setup mock for parsing arguments
        mock_parse_args.return_value = MagicMock()

        # Mock evaluation of config
        mock_evaluate.return_value = (
            {"aws_region": "us-west-2", "asg": {"name": ["asg1"]}, "ec2": {"name": ["ec2-1"]}, 
             "ecs": {"name": ["ecs1"]}, "rds": {"name": ["rds1"]}},
            ["ec2", "asg", "ecs", "rds"],
            "stop",
            "workspace_name",
            False,
            10
        )

        # Mock AWS session login
        mock_session = MagicMock()
        mock_aws_login.return_value = mock_session

        # Mock scheduler functions
        mock_asg_scheduler.return_value = ["asg1 stopped"]
        mock_ec2_scheduler.return_value = [{"InstanceId": "ec2-1", "State": "stopped"}]
        mock_ecs_scheduler.return_value = ["ecs1 stopped"]
        mock_rds_scheduler.return_value = ["rds1 stopped"]

        # Run the main function
        main()

        # Assertions for EC2
        mock_ec2_scheduler.assert_called_once_with(
            {"name": ["ec2-1"]},
            "stop",
            instance_attributes=['InstanceId', 'InstanceType', 'State', 'PrivateIpAddress', 'PublicIpAddress']
        )

        # Assertions for ASG
        mock_asg_scheduler.assert_called_once_with({"name": ["asg1"]}, "stop")

        # Assertions for ECS
        mock_ecs_scheduler.assert_called_once_with({"name": ["ecs1"]}, "stop")

        # Assertions for RDS
        mock_rds_scheduler.assert_called_once_with({"name": ["rds1"]}, "stop", instance_attributes=['DBInstanceIdentifier', 'DBInstanceStatus', 'DBInstanceClass', 'Engine', 'Endpoint'])

        # Verify the notification was sent
        mock_send_chat.assert_called()

    @patch('aws_resource_scheduler.utils.ecs.EcsModule.start_ecs_service')
    @patch('aws_resource_scheduler.utils.ecs.EcsModule.stop_ecs_service')
    @patch('aws_resource_scheduler.utils.ecs.EcsModule.get_ecs_service_status')
    def test_safe_execution(self, mock_get_status, mock_stop, mock_start):
        # Mock the behavior of get_ecs_service_status to simulate different scenarios
        mock_get_status.return_value = {
            "cluster_name": "test-cluster",
            "service_name": "test-service",
            "desired_count": 1,
            "running_count": 1,
            "status": "ACTIVE",
            "launch_type": "FARGATE",
            "task_definition": "test-task-def"
        }

        # Mock stop_ecs_service to raise an exception
        mock_stop.side_effect = Exception("Test Exception")

        # Initialize EcsModule with mocked data
        session = MagicMock()
        storage = MagicMock()
        ecs_module = EcsModule(session, storage, "workspace", no_wait=False, threads=2)

        # Call safe_execution with stop_ecs_service and service_data
        service_data = {
            "cluster_name": "test-cluster",
            "service_name": "test-service"
        }
        ecs_module.safe_execution(ecs_module.stop_ecs_service, service_data)

        # Verify that the error was logged and the message was appended to the scheduler_summary_message
        self.assertIn("Failed to process service test-service", ecs_module.scheduler_summary_message)

if __name__ == '__main__':
    unittest.main()
