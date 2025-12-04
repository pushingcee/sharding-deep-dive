#!/bin/bash

# Define arrays for containers and volumes
containers=(
    "worker-1" "worker-2" "worker-3" "worker-4"
    "single_instance" "master"
    "shard-1" "shard-2" "shard-3" "shard-4"
    "lookup-table"
)

volumes=(
    "postgres_master"
    "postgres_worker_1_data" "postgres_worker_2_data" "postgres_worker_3_data" "postgres_worker_4_data"
    "00-single-db_single_data"
    "shard_1_data" "shard_2_data" "shard_3_data" "shard_4_data"
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
