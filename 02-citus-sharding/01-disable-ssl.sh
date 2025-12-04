#!/bin/bash
# This script is used to disable ssl for the master and worker nodes, 
#you'll need to run it after the containers are started and 
#after that restart them in order for the ssl changes to take effect

echo "Setting ssl off for master"
docker exec -i master psql -U postgres -c "ALTER SYSTEM SET ssl = off;"
docker exec -i master psql -U postgres -c "SHOW ssl;"

for i in {1..4}
  do
    echo "Setting ssl off for Worker-$i"
    docker exec -i worker-$i psql -U postgres -c "ALTER SYSTEM SET ssl = off;"
    docker exec -i worker-$i psql -U postgres -c "SHOW ssl;"
  done
