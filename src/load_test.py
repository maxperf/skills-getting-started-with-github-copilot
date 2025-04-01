"""
Load Testing Script for High School Management System API
This script performs load testing using asyncio and aiohttp to simulate
many concurrent users accessing the application.
"""
import asyncio
import aiohttp
import time
import statistics
import argparse
import json
from datetime import datetime

# Base URL for the application
BASE_URL = "http://localhost:8000"

async def fetch_activities(session, user_id):
    """Simulate a user viewing activities"""
    start_time = time.time()
    try:
        async with session.get(f"{BASE_URL}/activities") as response:
            if response.status == 200:
                await response.json()
                return {
                    "user_id": user_id,
                    "endpoint": "/activities",
                    "status": response.status,
                    "response_time": time.time() - start_time
                }
            else:
                return {
                    "user_id": user_id,
                    "endpoint": "/activities",
                    "status": response.status,
                    "response_time": time.time() - start_time,
                    "error": f"Failed with status {response.status}"
                }
    except Exception as e:
        return {
            "user_id": user_id,
            "endpoint": "/activities",
            "status": 0,
            "response_time": time.time() - start_time,
            "error": str(e)
        }

async def signup_for_activity(session, user_id):
    """Simulate a user signing up for an activity"""
    start_time = time.time()
    
    # Randomly select an activity
    activity_name = "Chess Club"  # Fixed for reproducibility, could be randomized
    email = f"loadtest{user_id}@mergington.edu"
    
    try:
        async with session.post(
            f"{BASE_URL}/activities/{activity_name}/signup",
            params={"email": email}
        ) as response:
            await response.json()
            return {
                "user_id": user_id,
                "endpoint": f"/activities/{activity_name}/signup",
                "status": response.status,
                "response_time": time.time() - start_time
            }
    except Exception as e:
        return {
            "user_id": user_id,
            "endpoint": f"/activities/{activity_name}/signup",
            "status": 0,
            "response_time": time.time() - start_time,
            "error": str(e)
        }

async def simulate_user_session(user_id):
    """Simulate a complete user session"""
    async with aiohttp.ClientSession() as session:
        # First, user views activities
        view_result = await fetch_activities(session, user_id)
        
        # Then, user signs up for an activity
        signup_result = await signup_for_activity(session, user_id)
        
        return [view_result, signup_result]

async def run_load_test(num_users, ramp_up_time=1):
    """
    Run a load test with the specified number of users
    
    Args:
        num_users: Number of concurrent users to simulate
        ramp_up_time: Time (in seconds) to gradually add all users
    """
    print(f"Starting load test with {num_users} concurrent users (ramp up: {ramp_up_time}s)")
    
    start_time = time.time()
    test_results = []
    
    # Create tasks for all users with delay for ramp-up
    tasks = []
    for user_id in range(num_users):
        # Calculate delay for this user based on ramp-up time
        if ramp_up_time > 0 and num_users > 1:
            delay = (user_id / (num_users - 1)) * ramp_up_time
        else:
            delay = 0
            
        # Create task with delay
        tasks.append(
            asyncio.create_task(
                delayed_user_session(user_id, delay)
            )
        )
    
    # Wait for all tasks to complete
    results = await asyncio.gather(*tasks)
    for user_results in results:
        test_results.extend(user_results)
    
    total_time = time.time() - start_time
    
    # Process and report results
    return process_results(test_results, total_time, num_users)

async def delayed_user_session(user_id, delay):
    """Run a user session after a delay"""
    if delay > 0:
        await asyncio.sleep(delay)
    return await simulate_user_session(user_id)

def process_results(results, total_time, num_users):
    """Process and display test results"""
    # Group results by endpoint
    endpoints = {}
    for result in results:
        endpoint = result["endpoint"]
        if endpoint not in endpoints:
            endpoints[endpoint] = []
        endpoints[endpoint].append(result)
    
    # Calculate statistics
    stats = {
        "test_duration": total_time,
        "total_requests": len(results),
        "requests_per_second": len(results) / total_time,
        "concurrent_users": num_users,
        "endpoints": {}
    }
    
    # Process each endpoint
    for endpoint, endpoint_results in endpoints.items():
        response_times = [r["response_time"] for r in endpoint_results]
        success_count = sum(1 for r in endpoint_results if 200 <= r.get("status", 0) < 300)
        error_count = len(endpoint_results) - success_count
        
        stats["endpoints"][endpoint] = {
            "requests": len(endpoint_results),
            "success_rate": success_count / len(endpoint_results) if endpoint_results else 0,
            "error_count": error_count,
            "min_response_time": min(response_times) if response_times else 0,
            "max_response_time": max(response_times) if response_times else 0,
            "avg_response_time": statistics.mean(response_times) if response_times else 0,
            "p95_response_time": sorted(response_times)[int(len(response_times) * 0.95)] if len(response_times) >= 20 else "N/A"
        }
    
    # Print summary
    print(f"\n====== LOAD TEST RESULTS ======")
    print(f"Test duration: {total_time:.2f} seconds")
    print(f"Concurrent users: {num_users}")
    print(f"Total requests: {len(results)}")
    print(f"Requests per second: {len(results) / total_time:.2f}")
    
    for endpoint, data in stats["endpoints"].items():
        print(f"\n--- {endpoint} ---")
        print(f"Requests: {data['requests']}")
        print(f"Success rate: {data['success_rate'] * 100:.1f}%")
        print(f"Error count: {data['error_count']}")
        print(f"Response time (min/avg/max): {data['min_response_time']:.3f}s / {data['avg_response_time']:.3f}s / {data['max_response_time']:.3f}s")
        print(f"P95 response time: {data['p95_response_time'] if data['p95_response_time'] != 'N/A' else 'N/A'}")
    
    # Save results to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"load_test_results_{timestamp}.json"
    with open(filename, "w") as f:
        json.dump(stats, f, indent=2)
    
    print(f"\nDetailed results saved to: {filename}")
    
    return stats

async def main():
    """Parse arguments and run tests"""
    parser = argparse.ArgumentParser(description="Load Testing for High School Activities API")
    parser.add_argument("--users", type=int, default=50, help="Number of concurrent users to simulate")
    parser.add_argument("--ramp-up", type=float, default=5.0, help="Ramp-up time in seconds")
    args = parser.parse_args()
    
    await run_load_test(args.users, args.ramp_up)

if __name__ == "__main__":
    asyncio.run(main())