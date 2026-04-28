```sql
  WITH user_order_stats AS (
            SELECT 
                u.user_id,
                u.first_name,
                u.last_name,
                u.country,
                COUNT(o.order_id) as total_orders,
                SUM(o.total_amount) as total_spent,
                AVG(o.total_amount) as avg_order_value,
                MAX(o.order_date) as last_order_date,
                COUNT(CASE WHEN o.status = 'delivered' THEN 1 END) as delivered_orders,
                COUNT(CASE WHEN o.status = 'cancelled' THEN 1 END) as cancelled_orders
            FROM users u
            LEFT JOIN orders o ON u.user_id = o.user_id
            WHERE u.created_at >= CURRENT_DATE - INTERVAL '6 months'
            GROUP BY u.user_id, u.first_name, u.last_name, u.country
        ),
        product_performance AS (
            SELECT 
                p.product_id,
                p.name,
                p.category,
                p.price,
                COUNT(oi.order_id) as times_ordered,
                SUM(oi.quantity) as total_quantity_sold,
                SUM(oi.quantity * p.price) as total_revenue,
                COUNT(DISTINCT o.user_id) as unique_customers
            FROM products p
            LEFT JOIN order_items oi ON p.product_id = oi.product_id
            LEFT JOIN orders o ON oi.order_id = o.order_id
            WHERE o.order_date >= CURRENT_DATE - INTERVAL '6 months'
            GROUP BY p.product_id, p.name, p.category, p.price
        ),
        country_analytics AS (
            SELECT 
                u.country,
                COUNT(DISTINCT u.user_id) as total_users,
                COUNT(DISTINCT o.order_id) as total_orders,
                SUM(o.total_amount) as total_revenue,
                AVG(o.total_amount) as avg_order_value,
                COUNT(DISTINCT p.product_id) as unique_products_ordered
            FROM users u
            LEFT JOIN orders o ON u.user_id = o.user_id
            LEFT JOIN order_items oi ON o.order_id = oi.order_id
            LEFT JOIN products p ON oi.product_id = p.product_id
            WHERE u.created_at >= CURRENT_DATE - INTERVAL '6 months'
            GROUP BY u.country
        )
        SELECT 
            'User Analytics' as report_type,
            COUNT(*) as total_count,
            SUM(total_orders) as total_orders,
            SUM(total_spent) as total_revenue,
            AVG(avg_order_value) as average_value,
            COUNT(CASE WHEN total_orders > 10 THEN 1 END) as special_count
        FROM user_order_stats
        UNION ALL
        SELECT 
            'Product Analytics' as report_type,
            COUNT(*) as total_count,
            SUM(times_ordered) as total_orders,
            SUM(total_revenue) as total_revenue,
            AVG(total_quantity_sold) as average_value,
            COUNT(CASE WHEN total_revenue > 10000 THEN 1 END) as special_count
        FROM product_performance
        UNION ALL
        SELECT 
            'Country Analytics' as report_type,
            COUNT(*) as total_count,
            SUM(total_orders) as total_orders,
            SUM(total_revenue) as total_revenue,
            AVG(avg_order_value) as average_value,
            COUNT(CASE WHEN total_revenue > 50000 THEN 1 END) as special_count
        FROM country_analytics
```