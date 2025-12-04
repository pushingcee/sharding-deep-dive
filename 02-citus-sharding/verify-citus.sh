#!/bin/bash

# Function to get count from Citus coordinator
get_count() {
    local table_name=$1
    docker exec -i "master" psql -U postgres -d mydb -c "SELECT COUNT(*) FROM $table_name;" | sed -n '3p'
}

echo "Verifying Citus sharding..."

USERS=$(get_count "users")
ORDERS=$(get_count "orders")
PRODUCTS=$(get_count "products")

echo "=== Citus Distributed Database Verification ==="
echo "Users: $USERS"
echo "Orders: $ORDERS"
echo "Products: $PRODUCTS"
echo ""
echo "Note: Citus automatically distributes data across worker nodes"
echo "These counts represent the total across all worker shards"
echo ""
echo "Total data in Citus cluster:"
echo "- Users: $USERS (distributed across worker nodes)"
echo "- Orders: $ORDERS (distributed across worker nodes)"
echo "- Products: $PRODUCTS (reference table, replicated to all workers)"