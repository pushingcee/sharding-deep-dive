#!/bin/bash

docker exec -i master psql -U postgres -d mydb -c "ALTER SYSTEM SET citus.node_conninfo = 'sslmode=disable';"
docker exec -i master psql -U postgres -d mydb -c "SELECT pg_reload_conf();"

for i in {1..4}
do
  docker exec -i worker-$i psql -U postgres -d mydb -c "ALTER SYSTEM SET citus.node_conninfo = 'sslmode=disable';"
  docker exec -i worker-$i psql -U postgres -d mydb -c "SELECT pg_reload_conf();"
done

docker exec -i master psql -U postgres -d mydb -c "SELECT * from citus_set_coordinator_host('master', 5432);"

for i in {1..4}
do
  docker exec -i master psql -U postgres -d mydb -c "SELECT citus_add_node('worker-$i', 5432)"
done

echo "Checking active workers..."
docker exec -i master psql -U postgres -d mydb -c "SELECT * FROM citus_get_active_worker_nodes();"

echo "Final node status..."
docker exec -i master psql -U postgres -d mydb -c "SELECT * FROM pg_dist_node ORDER BY nodeid;"
