# Database Sharding Exploration Project

A comprehensive comparison of PostgreSQL database architectures, from single instances to distributed sharding strategies. This project demonstrates four different approaches to scaling databases with an e-commerce use case.

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture Approaches](#architecture-approaches)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Technology Stack](#technology-stack)
- [Data Generation](#data-generation)
- [Performance Testing](#performance-testing)
- [Verification Scripts](#verification-scripts)
- [Development](#development)
- [Troubleshooting](#troubleshooting)

## 🎯 Overview

This project implements an e-commerce data model across four different database architectures to demonstrate:

- **Single Database**: Traditional PostgreSQL setup
- **Manual Sharding**: Application-level sharding with consistent hashing
- **Citus Sharding**: PostgreSQL extension for distributed databases
- **Lookup Table Sharding**: Manual sharding with centralized routing table

### Key Features

- **Consistent Hashing**: Identical UUID-based sharding algorithm across Python and Java
- **E-commerce Schema**: Users, Orders, Products, Order Items with realistic relationships
- **Performance Testing**: Built-in queries for cross-shard analytics and load testing
- **Docker Orchestration**: Complete containerized environments for each architecture
- **Data Generation**: Faker-based synthetic data generation with configurable volumes

## 🏗️ Architecture Approaches

### 1. Single Database (`00-single-db/`)
- **Setup**: Single PostgreSQL 16 instance
- **Port**: 5432
- **Use Case**: Traditional monolithic database approach
- **Pros**: Simple, ACID compliance, no complexity
- **Cons**: Single point of failure, limited scalability

### 2. Manual Sharding (`01-manual-sharding/`)
- **Setup**: 4 PostgreSQL instances (ports 5433-5436)
- **Sharding Key**: user_id (UUID)
- **Algorithm**: SHA-1 hash of UUID bytes modulo 4
- **Data Co-location**: Orders and OrderItems co-located with Users
- **Products**: Replicated across all shards (reference table)
- **Routing**: Application-level in Java Spring Boot

### 3. Citus Sharding (`02-citus-sharding/`)
- **Setup**: Citus coordinator + worker nodes
- **Sharding**: Automatic distribution using Citus extension
- **Management**: Built-in rebalancing and query planning
- **Use Case**: PostgreSQL-native distributed computing

### 4. Lookup Table Sharding (`03-manual-sharding-lookup-table/`)
- **Setup**: 4 shards + centralized routing table
- **Routing**: Database-stored shard location mapping
- **Flexibility**: Dynamic shard assignment and migration capability
- **Overhead**: Additional lookup query for routing

## ⚡ Quick Start

### Prerequisites
```bash
# Required tools
docker && docker-compose
python 3.8+
java 23 (with Maven)
git
```

### 1. Environment Setup
```bash
# Clone and enter project
git clone <repository-url>
cd sharding_partitioning_postgres_claude

# Setup Python environment
cd python
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows
pip install -r requirements.txt
cd ..
```

### 2. Choose Your Architecture

#### Single Database
```bash
# Start database
docker-compose -f 00-single-db/docker-compose.yaml up -d

# Generate test data
cd python
python db_setup.py --mode single --users 10000 --products 1000 --orders-per-user 5

# Start API
cd ../java/e-commerce-simple-api
mvn spring-boot:run
```

#### Manual Sharding
```bash
# Start sharded databases
docker-compose -f 01-manual-sharding/docker-compose.yaml up -d

# Generate distributed data
cd python
python db_setup.py --mode sharded --users 10000 --products 1000 --orders-per-user 5

# Verify distribution
../01-manual-sharding/verify-sharding.sh

# Start API with sharded profile
cd ../java/e-commerce-simple-api
mvn spring-boot:run -Dspring-boot.run.profiles=sharded
```

### 3. Test the API
```bash
# Health check
curl http://localhost:8080/actuator/health

# Get user by ID
curl http://localhost:8080/users/{user-id}

# Run heavy analytics query
curl http://localhost:8080/heavy-queries/user-order-analytics
```

## 📁 Project Structure

```
├── 00-single-db/                    # Single database setup
│   ├── docker-compose.yaml          # PostgreSQL single instance
│   └── verify-single.sh            # Data verification
├── 01-manual-sharding/             # Manual sharding setup
│   ├── docker-compose.yaml         # 4 PostgreSQL instances
│   └── verify-sharding.sh          # Shard distribution verification
├── 02-citus-sharding/              # Citus distributed setup
│   ├── docker-compose-sharded-citus.yaml
│   └── verify-citus.sh
├── 03-manual-sharding-lookup-table/ # Lookup table routing
│   ├── docker-compose.yaml
│   └── verify-sharding-lookup.sh
├── python/                          # Data generation & utilities
│   ├── db_setup.py                 # Main data generation script
│   ├── requirements.txt            # Python dependencies
│   └── utilities/
│       ├── commons/
│       │   ├── DataGenerator.py    # Faker-based data generation
│       │   └── DbConfig.py         # Database configuration
│       ├── database/
│       │   ├── table_manager.py    # Schema management
│       │   └── data_generator.py   # Data insertion logic
│       └── generators/
│           └── base_generator.py   # Base data generation
├── java/e-commerce-simple-api/      # Spring Boot REST API
│   ├── pom.xml                     # Maven dependencies
│   ├── src/main/java/org/learn/
│   │   ├── configuration/          # Database configurations
│   │   │   ├── sharded/            # Manual sharding config
│   │   │   │   ├── ShardRouter.java        # Consistent hashing
│   │   │   │   └── ManualShardingDataSourceConfig.java
│   │   │   ├── lookup/             # Lookup table config
│   │   │   └── single/             # Single DB config
│   │   ├── domain/                 # JPA entities
│   │   │   ├── User.java
│   │   │   ├── Order.java
│   │   │   └── product/
│   │   ├── repository/             # Data access layer
│   │   │   ├── single/             # Single DB repositories
│   │   │   ├── sharded/            # Sharded repositories
│   │   │   └── lookup/             # Lookup table repositories
│   │   ├── service/                # Business logic
│   │   └── controller/             # REST endpoints
│   └── src/main/resources/
│       ├── application.properties          # Single DB config
│       └── application-sharded.properties  # Sharded config
└── cleanup.sh                      # Docker cleanup script
```

## 🛠️ Technology Stack

### Backend
- **Java 23** with **Spring Boot 3.4.4**
- **Spring Data JPA** for ORM
- **PostgreSQL 16** database
- **Maven** for dependency management

### Data Generation
- **Python 3.8+**
- **psycopg 3** PostgreSQL adapter
- **Faker** for synthetic data
- **Threading** for parallel processing

### Infrastructure
- **Docker & Docker Compose** for orchestration
- **Citus** PostgreSQL extension for distribution

### Key Dependencies
```xml
<!-- Java -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
</dependency>
```

```python
# Python
psycopg==3.1.18
Faker==24.4.0
```

## 📊 Data Generation

### Schema Overview
```sql
-- Users table (sharded by user_id)
users: id(UUID), name, email, address, phone, created_at

-- Orders table (co-located with users)
orders: id(UUID), user_id(UUID), total_amount, status, created_at

-- Products table (reference table, replicated)
products: id(UUID), name, price, category, description, stock

-- Order Items table (co-located with orders)
order_items: order_id(UUID), product_id(UUID), quantity, price
```

### Generation Commands

#### Single Database
```bash
cd python
python db_setup.py --mode single --users 50000 --products 5000 --orders-per-user 3
```

#### Manual Sharding
```bash
cd python
python db_setup.py --mode sharded --users 50000 --products 5000 --orders-per-user 3
```

#### Citus Sharding
```bash
cd python  
python db_setup.py --mode citus --users 50000 --products 5000 --orders-per-user 3
```

#### Lookup Table Sharding
```bash
cd python
python db_setup.py --mode lookup --users 50000 --products 5000 --orders-per-user 3
```

### Advanced Options
```bash
# Enable debug logging
python db_setup.py --mode sharded --users 1000 --debug

# Custom batch sizes
python db_setup.py --mode single --users 100000 --batch-size 10000

# Specify items per order
python db_setup.py --mode sharded --users 10000 --items-per-order 5
```

## 📈 Performance Testing

### Built-in Heavy Queries

The project includes realistic analytics queries for performance testing:

```bash
# User order analytics (cross-shard aggregation)
curl http://localhost:8080/heavy-queries/user-order-analytics

# Product popularity analysis
curl http://localhost:8080/heavy-queries/product-analytics  

# Recent high-value orders
curl http://localhost:8080/heavy-queries/high-value-orders
```

### Custom Performance Testing
```java
// Located in: HeavyQueryService.java
public List<AnalyticsResult> getUserOrderAnalytics() {
    // Complex cross-shard aggregation query
    // Tests sharding performance under load
}
```

## ✅ Verification Scripts

### Verify Data Distribution
```bash
# Manual sharding verification
./01-manual-sharding/verify-sharding.sh

# Lookup table sharding verification  
./03-manual-sharding-lookup-table/verify-sharding-lookup.sh

# Citus distribution verification
./02-citus-sharding/verify-citus.sh

# Single database verification
./00-single-db/verify-single.sh
```

Example output:
```
=== Shard Distribution Verification ===
Shard 1 (port 5433): 12,487 users, 62,435 orders
Shard 2 (port 5434): 12,513 users, 62,565 orders  
Shard 3 (port 5435): 12,450 users, 62,250 orders
Shard 4 (port 5436): 12,550 users, 62,750 orders
Total: 50,000 users, 250,000 orders
```

## 🔧 Development

### Running Different Profiles

#### Single Database Profile (Default)
```bash
cd java/e-commerce-simple-api
mvn spring-boot:run
```

#### Sharded Database Profile
```bash
cd java/e-commerce-simple-api
mvn spring-boot:run -Dspring-boot.run.profiles=sharded
```

### Configuration Files
- `application.properties`: Single database configuration
- `application-sharded.properties`: Manual sharding configuration

### Key Implementation Details

#### Consistent Hashing Algorithm
Both Python and Java implement identical sharding logic:

```python
# Python implementation
def get_shard_index(user_id_uuid):
    hash_digest = hashlib.sha1(user_id_uuid.bytes).digest()
    hash_int = int.from_bytes(hash_digest[:8], 'big')
    return hash_int % NUM_SHARDS
```

```java
// Java implementation  
public int getShardIndex(UUID userId) {
    byte[] uuidBytes = convertUuidToBytes(userId);
    byte[] hashDigest = sha1.digest(uuidBytes);
    long hashInt = convertBytesToLong(hashDigest);
    return (int) (hashInt % NUM_SHARDS);
}
```

### Database Connection Configuration

#### Sharded Configuration
```java
@Bean("shard1DataSource")
public DataSource shard1DataSource() {
    return DataSourceBuilder.create()
        .url("jdbc:postgresql://localhost:5433/mydb")
        .username("postgres")
        .build();
}
```

## 🔍 Troubleshooting

### Common Issues

#### Database Connection Issues
```bash
# Check if containers are running
docker ps

# Check container logs
docker logs shard-1

# Restart specific container
docker-compose -f 01-manual-sharding/docker-compose.yaml restart shard-1
```

#### Data Generation Issues
```bash
# Enable debug mode
python db_setup.py --mode sharded --users 1000 --debug

# Check database connectivity
python -c "import psycopg; conn = psycopg.connect('host=localhost port=5433 user=postgres dbname=mydb')"
```

#### Java Application Issues
```bash
# Check active profile
mvn spring-boot:run -Dspring-boot.run.profiles=sharded -Dlogging.level.org.learn=DEBUG

# Verify data source beans
# Look for auto-configuration conflicts in logs
```

### Clean Environment
```bash
# Complete cleanup
./cleanup.sh

# Remove all containers and volumes
docker system prune -a --volumes
```

### Performance Issues
- **Docker Resources**: Ensure adequate CPU/memory allocation
- **Batch Size Tuning**: Adjust batch sizes in constants.py
- **Connection Pooling**: Monitor connection pool settings
- **Query Optimization**: Use EXPLAIN ANALYZE on slow queries

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is for educational purposes demonstrating database sharding concepts.

---

**Note**: This project is optimized for development and learning environments. Production deployments would require additional considerations for security, monitoring, backup strategies, and high availability configurations.