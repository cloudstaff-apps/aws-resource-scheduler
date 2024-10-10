# -*- coding: utf-8 -*-
import logging
import time
from concurrent.futures import ThreadPoolExecutor


class AuroraModule:
    """
    Manages Aurora cluster scheduling tasks such as start, stop, and checking cluster status.
    """

    def __init__(self, session, no_wait=False, threads=10):
        """
        Initializes the Aurora module with a provided AWS session.
        """
        self.session = session
        self.client = self.session.client('rds')
        self.scheduler_summary_message = []
        self.no_wait = no_wait
        self.threads = threads

    def describe_aurora_clusters(self, cluster_identifiers=None, tags=None, cluster_attributes=None):
        """
        Describes the Aurora clusters based on identifiers or tags.
        """
        response = self.client.describe_db_clusters()
        aurora_clusters = []

        for cluster in response['DBClusters']:
            if cluster_identifiers and cluster['DBClusterIdentifier'] not in cluster_identifiers:
                continue
            if tags:
                response_tags = self.client.list_tags_for_resource(ResourceName=cluster['DBClusterArn'])
                tags_dict = {tag['Key']: tag['Value'] for tag in response_tags.get('TagList', [])}
                if not all(tags_dict.get(k) == v for k, v in tags.items()):
                    continue

            cluster_data = {'DBClusterIdentifier': cluster['DBClusterIdentifier']}
            if cluster_attributes:
                for attribute in cluster_attributes:
                    if attribute == 'Endpoint':
                        cluster_data['Endpoint'] = cluster.get('Endpoint')
                    else:
                        cluster_data[attribute] = cluster.get(attribute)
            aurora_clusters.append(cluster_data)

        return aurora_clusters

    def wait_status(self, cluster_identifier, expected_status):
        while True:
            status = self.cluster_status(cluster_identifier)
            if status == expected_status:
                return
            logging.info(f"Waiting for {cluster_identifier} to reach {expected_status} state...")
            time.sleep(30)

    def start_cluster(self, cluster_identifier):
        """
        Starts the specified Aurora cluster if not already started.
        """
        current_status = self.cluster_status(cluster_identifier)
        if current_status in ["available", "starting"]:
            self.scheduler_summary_message.append(f"{cluster_identifier} is already Available or Starting.")
            return
        self.client.start_db_cluster(DBClusterIdentifier=cluster_identifier)
        if not self.no_wait:
            self.wait_status(cluster_identifier, "available")
            self.scheduler_summary_message.append(f"{cluster_identifier} started successfully.")
        else:
            self.scheduler_summary_message.append(f"{cluster_identifier} start initiated (no-wait mode).")

    def stop_cluster(self, cluster_identifier):
        """
        Stops the specified Aurora cluster if not already stopped.
        """
        current_status = self.cluster_status(cluster_identifier)
        if current_status in ["stopped", "stopping"]:
            self.scheduler_summary_message.append(f"{cluster_identifier} is already in Stopping or Stopped state.")
            return
        self.client.stop_db_cluster(DBClusterIdentifier=cluster_identifier)
        if not self.no_wait:
            self.wait_status(cluster_identifier, "stopped")
            self.scheduler_summary_message.append(f"{cluster_identifier} stopped successfully.")
        else:
            self.scheduler_summary_message.append(f"{cluster_identifier} stop initiated (no-wait mode).")

    def cluster_status(self, cluster_identifier):
        response = self.client.describe_db_clusters(
            DBClusterIdentifier=cluster_identifier
        )
        return response['DBClusters'][0]['Status']

    def schedule_aurora(self, data, action, cluster_attributes=None):
        aurora_clusters = []

        if 'name' in data:
            identifiers = data['name'] if isinstance(data['name'], list) else [data['name']]
            aurora_clusters.extend(self.describe_aurora_clusters(cluster_identifiers=identifiers, cluster_attributes=cluster_attributes))

        if 'tags' in data:
            aurora_clusters.extend(self.describe_aurora_clusters(tags=data['tags'], cluster_attributes=cluster_attributes))

        unique_clusters = {cluster['DBClusterIdentifier']: cluster for cluster in aurora_clusters}

        if action == 'status':
            return list(unique_clusters.values())

        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            if action == "stop":
                executor.map(self.stop_cluster, unique_clusters.keys())
            elif action == "start":
                executor.map(self.start_cluster, unique_clusters.keys())

        # Collect cluster details for summary
        cluster_details = []
        for cluster_id in unique_clusters.keys():
            cluster_info = {
                'DBClusterIdentifier': cluster_id,
                'action': action,
                'Status': self.cluster_status(cluster_id)
            }
            cluster_details.append(cluster_info)

        return cluster_details
