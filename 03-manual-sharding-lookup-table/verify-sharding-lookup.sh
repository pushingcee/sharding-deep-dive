#!/bin/bash

# Function to get count from a specific shard and table
get_count() {
    local shard_name=$1
    local table_name=$2
    docker exec -i "$shard_name" psql -U postgres -d mydb -c "SELECT COUNT(*) FROM $table_name;" | sed -n '3p'
}

print_count() {
    local item=$1
    local shard_name=$2
    local count=$3
    echo "$item in $shard_name: $count"
}

echo "Verifying sharding..."

ORDERS_1=$(get_count "shard-1" "orders")
ORDERS_2=$(get_count "shard-2" "orders")
ORDERS_3=$(get_count "shard-3" "orders")
ORDERS_4=$(get_count "shard-4" "orders")

print_count "Orders" "shard 1" "$ORDERS_1"
print_count "Orders" "shard 2" "$ORDERS_2"
print_count "Orders" "shard 3" "$ORDERS_3"
print_count "Orders" "shard 4" "$ORDERS_4"
echo "Total orders: $((ORDERS_1 + ORDERS_2 + ORDERS_3 + ORDERS_4))"

USERS_1=$(get_count "shard-1" "users")
USERS_2=$(get_count "shard-2" "users")
USERS_3=$(get_count "shard-3" "users")
USERS_4=$(get_count "shard-4" "users")

print_count "Users" "shard 1" "$USERS_1"
print_count "Users" "shard 2" "$USERS_2"
print_count "Users" "shard 3" "$USERS_3"
print_count "Users" "shard 4" "$USERS_4"
echo "Total users: $((USERS_1 + USERS_2 + USERS_3 + USERS_4))"

PRODUCTS_1=$(get_count "shard-1" "products")
PRODUCTS_2=$(get_count "shard-2" "products")
PRODUCTS_3=$(get_count "shard-3" "products")
PRODUCTS_4=$(get_count "shard-4" "products")

print_count "Products" "shard 1" "$PRODUCTS_1"
print_count "Products" "shard 2" "$PRODUCTS_2"
print_count "Products" "shard 3" "$PRODUCTS_3"
print_count "Products" "shard 4" "$PRODUCTS_4"
echo "Products is a reference table so it's the same for all shards"
echo ""
echo "=== Manual Sharding with Lookup Table Summary ==="
echo "Total users: $((USERS_1 + USERS_2 + USERS_3 + USERS_4))"
echo "Total orders: $((ORDERS_1 + ORDERS_2 + ORDERS_3 + ORDERS_4))"
echo "Total products: $PRODUCTS_1 (replicated across all 4 shards)"
echo ""
echo "Lookup table entries:"
LOOKUP_COUNT=$(docker exec -i "lookup-table" psql -U postgres -d mydb -c "SELECT COUNT(*) FROM user_data_shard;" | sed -n '3p')
echo "User-to-shard mappings: $LOOKUP_COUNT"