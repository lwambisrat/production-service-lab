# System Architecture

## Overview

This system simulates a production ride-booking platform built using microservices.

It consists of:

* Nginx reverse proxy
* Service A (Ride Booking API)
* Service B (Driver Matching Service)
* Service C (Ride Dispatch Service)

---

## Architecture Diagram

Client
↓
Nginx (Port 80)
↓
Service A (Port 3001)
↓
Service B (Port 3002)
↓
Service C (Port 3003)
↓
Service A Callback

---

## Detailed Flow

### Step 1: Client Request

The client sends:

GET /service-a/greet-service-b

Nginx receives this request.

---

### Step 2: Nginx Routing

Nginx removes:

/service-a/

and forwards to:

Service A → /greet-service-b

---

### Step 3: Service A Processing

Service A:

* receives request
* creates request_id if missing
* creates ride payload
* forwards request to Service B

Example:

Pickup:
Westlands

Dropoff:
CBD

---

### Step 4: Service B Driver Matching

Service B:

* reads ride request
* checks available drivers
* compares driver locations
* picks nearest driver

Example:

Driver:
Brian

Area:
Westlands

ETA:
3 minutes

---

### Step 5: Service C Dispatch

Service C:

* receives matched driver
* dispatches ride
* sends callback to Service A

---

### Step 6: Service A Callback

Service A confirms ride dispatch.

This completes the transaction.

---

## Service Discovery

Uses:

/etc/hosts

Mappings:

127.0.0.1 service-a.internal
127.0.0.1 service-b.internal
127.0.0.1 service-c.internal

Purpose:

Avoid hardcoded IP addresses.

---

## Security Design

Public:

* Nginx
* Service A only

Internal:

* Service B
* Service C

Protection:

Bound to localhost only.

Meaning:

External users cannot directly access internal services.

---

## Logging Flow

Every service logs:

* timestamp
* request_id
* service
* event
* path
* status

This allows tracing.

Example:

ride_request_received
→ driver_matched
→ ride_dispatched
→ callback_received

---

## Recovery Design

Managed by:

systemd

Capabilities:

* auto restart
* auto start on reboot
* operational logs
* service dependency ordering
