#!/bin/bash

# Function to get count from single database
get_count() {
    local table_name=$1
    docker exec -i "single_instance" psql -U postgres -d mydb -c "SELECT COUNT(*) FROM $table_name;" | sed -n '3p'
}

echo "Verifying single database..."

USERS=$(get_count "users")
ORDERS=$(get_count "orders")
PRODUCTS=$(get_count "products")

echo "=== Single Database Verification ==="
echo "Users: $USERS"
echo "Orders: $ORDERS"
echo "Products: $PRODUCTS"
echo ""
echo "Total data in single database:"
echo "- Users: $USERS"
echo "- Orders: $ORDERS" 
echo "- Products: $PRODUCTS"