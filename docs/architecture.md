# System Architecture

## Overview

This system simulates a production ride-booking platform built using microservices.

It consists of:

* Nginx reverse proxy
* ride-booking (Ride Booking API)
* driver-matching (Driver Matching Service)
* ride-dispatch (Ride Dispatch Service)

---

## Architecture Diagram

Client
↓
Nginx (Port 80)
↓
ride-booking (Port 3001)
↓
driver-matching (Port 3002)
↓
ride-dispatch (Port 3003)
↓
ride-booking Callback

---

## Detailed Flow

### Step 1: Client Request

The client sends:

POST /ride/request

Nginx receives this request on port 80.

---

### Step 2: Nginx Routing

Nginx forwards every path (`location /`) to ride-booking unchanged:

ride-booking → POST /ride/request

The path is not rewritten. Nginx also injects/propagates the `X-Request-ID`
trace header. Only `/nginx-health` is answered by Nginx itself.

---

### Step 3: ride-booking Processing

ride-booking:

* receives request
* creates request_id if missing
* creates ride payload
* forwards request to driver-matching

Example:

Pickup:
Westlands

Dropoff:
CBD

---

### Step 4: driver-matching

driver-matching:

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

### Step 5: ride-dispatch

ride-dispatch:

* receives matched driver
* dispatches ride
* sends callback to ride-booking

---

### Step 6: ride-booking Callback

ride-booking confirms ride dispatch.

This completes the transaction.

---

## Service Discovery

Uses:

/etc/hosts

Mappings:

127.0.0.1 ride-booking.internal
127.0.0.1 driver-matching.internal
127.0.0.1 ride-dispatch.internal

Purpose:

Avoid hardcoded IP addresses.

---

## Security Design

Public:

* Nginx
* ride-booking only

Internal:

* driver-matching
* ride-dispatch

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

ride_request_received   (ride-booking)
→ driver_matched          (driver-matching)
→ ride_dispatch_started   (ride-dispatch)
→ ride_dispatch_confirmed (ride-booking callback)

---

## Recovery Design

Managed by:

systemd

Capabilities:

* auto restart
* auto start on reboot
* operational logs
* service dependency ordering
