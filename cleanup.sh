#!/bin/bash

containers=(
    # Citus containers
    "worker-1" "worker-2" "worker-3" "worker-4" "master"
    # Single DB container
    "single_instance"
    # Manual sharding containers
    "shard-1" "shard-2" "shard-3" "shard-4"
    # Lookup table container
    "lookup-table"
    # Monitoring containers (01-manual-sharding)
    "postgres-exporter-shard1" "postgres-exporter-shard2"
    "postgres-exporter-shard3" "postgres-exporter-shard4"
    "otel-collector" "prometheus" "grafana"
)

# Volume names as defined in docker-compose files
# Docker Compose prefixes these with the project directory name
volumes=(
    # 00-single-db volumes
    "00-single-db_single_data"
    # 01-manual-sharding volumes
    "01-manual-sharding_shard_1_data"
    "01-manual-sharding_shard_2_data"
    "01-manual-sharding_shard_3_data"
    "01-manual-sharding_shard_4_data"
    "01-manual-sharding_grafana-storage"
    # 02-citus-sharding volumes
    "02-citus-sharding_master"
    "02-citus-sharding_worker_1_data"
    "02-citus-sharding_worker_2_data"
    "02-citus-sharding_worker_3_data"
    "02-citus-sharding_worker_4_data"
    # 03-manual-sharding-lookup-table volumes
    "03-manual-sharding-lookup-table_lookup_data"
    "03-manual-sharding-lookup-table_shard_1_data"
    "03-manual-sharding-lookup-table_shard_2_data"
    "03-manual-sharding-lookup-table_shard_3_data"
    "03-manual-sharding-lookup-table_shard_4_data"
)

stop_containers() {
    echo "Stopping containers..."
    for container in "${containers[@]}"; do
        docker container stop "$container" 2>/dev/null
    done
}

remove_containers() {
    echo "Removing containers..."
    for container in "${containers[@]}"; do
        docker container rm "$container" 2>/dev/null
    done
}

remove_volumes() {
    echo "Removing volumes..."
    for volume in "${volumes[@]}"; do
        docker volume rm "$volume" 2>/dev/null
    done
}

echo "Starting cleanup process..."

stop_containers
remove_containers
remove_volumes

echo "Cleanup completed successfully!"
