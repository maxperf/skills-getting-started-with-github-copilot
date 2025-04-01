"""
Load Testing Script for High School Management System API
This script performs load testing using asyncio and aiohttp to simulate
many concurrent users accessing the application.

It also includes a maximum throughput test to find the highest load
that can be handled while maintaining a 99.99% success rate.
"""
import asyncio
import aiohttp
import time
import statistics
import argparse
import json
import random
from datetime import datetime

# Base URL for the application
BASE_URL = "http://localhost:8000"

# SLA parameters
SLA_PARAMETERS = {
    "error_rate_threshold": 0.0001,  # 0.01% SLA means maximum allowed error rate is 0.01%
    "response_time_threshold": 1.0,   # Maximum allowed average response time in seconds
}

# List of available activities (will be populated dynamically)
AVAILABLE_ACTIVITIES = []

# Generate a unique timestamp to prevent duplicate signups across test runs
TEST_RUN_ID = int(time.time())

async def fetch_activities(session, user_id):
    """Simulate a user viewing activities and return the list of activities"""
    start_time = time.time()
    global AVAILABLE_ACTIVITIES
    
    try:
        async with session.get(f"{BASE_URL}/activities") as response:
            if response.status == 200:
                activities_data = await response.json()
                
                # Store available activities for signup
                if not AVAILABLE_ACTIVITIES:
                    # The activities are returned as a dictionary with activity names as keys
                    AVAILABLE_ACTIVITIES = list(activities_data.keys())
                    print(f"Available activities: {', '.join(AVAILABLE_ACTIVITIES)}")
                
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
    
    # Select an activity from available activities
    if AVAILABLE_ACTIVITIES:
        activity_name = AVAILABLE_ACTIVITIES[user_id % len(AVAILABLE_ACTIVITIES)]
    else:
        # Fallback to Chess Club if no activities were loaded
        activity_name = "Chess Club"
    
    # Create a unique email using both user_id and TEST_RUN_ID to prevent duplicates
    # across test runs
    email = f"loadtest{user_id}_{TEST_RUN_ID}@mergington.edu"
    
    try:
        # URL encode the activity name for spaces and special characters
        activity_name_encoded = activity_name.replace(" ", "%20")
        
        async with session.post(
            f"{BASE_URL}/activities/{activity_name_encoded}/signup",
            params={"email": email}
        ) as response:
            response_body = await response.text()
            
            # Consider 200 (success) and 400 (already signed up) as "successful" responses
            # for the purpose of measuring throughput
            is_success = response.status == 200 or (response.status == 400 and "already signed up" in response_body)
            
            return {
                "user_id": user_id,
                "endpoint": f"/activities/{activity_name}/signup",
                "status": response.status if is_success else response.status,
                "response_time": time.time() - start_time,
                "is_business_success": is_success,
                "body": response_body[:100] + "..." if len(response_body) > 100 else response_body
            }
    except Exception as e:
        return {
            "user_id": user_id,
            "endpoint": f"/activities/{activity_name}/signup",
            "status": 0,
            "response_time": time.time() - start_time,
            "error": str(e),
            "is_business_success": False
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
    
    # Pre-populate the activities list
    async with aiohttp.ClientSession() as session:
        await fetch_activities(session, 0)
    
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

def calculate_success_rate(results):
    """
    Calculate the overall success rate from test results
    For signup requests, we consider both 200 and 400 (already signed up) as "business successes"
    """
    success_count = sum(1 for r in results if (
        (200 <= r.get("status", 0) < 300) or
        r.get("is_business_success", False)
    ))
    return success_count / len(results) if results else 0

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
        "success_rate": calculate_success_rate(results),
        "endpoints": {}
    }
    
    # Process each endpoint
    for endpoint, endpoint_results in endpoints.items():
        response_times = [r["response_time"] for r in endpoint_results]
        
        # Count both HTTP and business successes
        http_success_count = sum(1 for r in endpoint_results if 200 <= r.get("status", 0) < 300)
        business_success_count = sum(1 for r in endpoint_results if r.get("is_business_success", False))
        
        # For signup, both 200 and 400 (already signed up) can be considered business successes
        combined_success_count = http_success_count
        if "signup" in endpoint:
            combined_success_count = business_success_count
            
        error_count = len(endpoint_results) - combined_success_count
        
        stats["endpoints"][endpoint] = {
            "requests": len(endpoint_results),
            "http_success_rate": http_success_count / len(endpoint_results) if endpoint_results else 0,
            "business_success_rate": combined_success_count / len(endpoint_results) if endpoint_results else 0,
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
    print(f"Overall success rate: {stats['success_rate'] * 100:.4f}%")
    print(f"Error rate: {(1 - stats['success_rate']) * 100:.4f}%")
    
    for endpoint, data in stats["endpoints"].items():
        print(f"\n--- {endpoint} ---")
        print(f"Requests: {data['requests']}")
        print(f"HTTP Success rate: {data['http_success_rate'] * 100:.2f}%")
        
        if "signup" in endpoint:
            print(f"Business Success rate (including 'already signed up'): {data['business_success_rate'] * 100:.2f}%") 
            
        print(f"Error count: {data['error_count']}")
        print(f"Response time (min/avg/max): {data['min_response_time']:.3f}s / {data['avg_response_time']:.3f}s / {data['max_response_time']:.3f}s")
        print(f"P95 response time: {data['p95_response_time'] if data['p95_response_time'] != 'N/A' else 'N/A'}")
        
        # Print some sample errors
        error_samples = [r.get("error") for r in endpoint_results if "error" in r][:3]
        if error_samples:
            print(f"Sample errors: {error_samples}")
    
    # Save results to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"load_test_results_{timestamp}.json"
    with open(filename, "w") as f:
        json.dump(stats, f, indent=2)
    
    print(f"\nDetailed results saved to: {filename}")
    
    return stats

async def find_maximum_throughput():
    """
    Find the maximum throughput that maintains the SLA requirements
    using a binary search approach
    """
    print("\n====== MAXIMUM THROUGHPUT TEST ======")
    print(f"Finding maximum throughput while maintaining {(1-SLA_PARAMETERS['error_rate_threshold'])*100:.4f}% success rate")
    
    lower_bound = 10  # Start with a reasonable lower bound
    upper_bound = 200  # Start with a reasonable upper bound
    max_throughput = lower_bound
    max_rps = 0
    
    # First do a test with the lower bound to ensure it's successful
    stats = await run_load_test(lower_bound, ramp_up_time=2)
    success_rate = stats["success_rate"]
    
    if success_rate < (1 - SLA_PARAMETERS["error_rate_threshold"]):
        print(f"\nWarning: Even with {lower_bound} users, success rate is below threshold: {success_rate*100:.4f}%")
        print("Application may have underlying issues preventing high throughput")
        return lower_bound, stats["requests_per_second"]
    
    # Then test the upper bound
    stats = await run_load_test(upper_bound, ramp_up_time=5)
    success_rate = stats["success_rate"]
    
    if success_rate >= (1 - SLA_PARAMETERS["error_rate_threshold"]):
        # If upper bound is successful, increase until we find the limit
        step_size = 50
        current_users = upper_bound + step_size
        
        while True:
            print(f"\nTrying increased load: {current_users} users")
            stats = await run_load_test(current_users, ramp_up_time=5)
            success_rate = stats["success_rate"]
            
            if success_rate >= (1 - SLA_PARAMETERS["error_rate_threshold"]):
                # Still successful, keep going higher
                max_throughput = current_users
                max_rps = stats["requests_per_second"]
                current_users += step_size
            else:
                # Found a failing point, now we know our upper bound
                upper_bound = current_users
                break
                
            if current_users > 1000:  # Safety limit
                print("Reached safety limit. System handling load extremely well.")
                max_throughput = current_users
                max_rps = stats["requests_per_second"]
                return max_throughput, max_rps
    else:
        # Binary search between lower and upper bounds
        while upper_bound - lower_bound > 5:  # Precision of 5 users
            mid = (lower_bound + upper_bound) // 2
            print(f"\nTrying {mid} users (binary search between {lower_bound} and {upper_bound})")
            
            stats = await run_load_test(mid, ramp_up_time=5)
            success_rate = stats["success_rate"]
            
            if success_rate >= (1 - SLA_PARAMETERS["error_rate_threshold"]):
                # This load is acceptable, try higher
                lower_bound = mid
                max_throughput = mid
                max_rps = stats["requests_per_second"]
            else:
                # This load exceeds SLA threshold, try lower
                upper_bound = mid
    
    # Final test with the maximum identified throughput to confirm
    stats = await run_load_test(max_throughput, ramp_up_time=5)
    
    print("\n====== MAXIMUM THROUGHPUT RESULTS ======")
    print(f"Maximum users while maintaining {(1-SLA_PARAMETERS['error_rate_threshold'])*100:.4f}% success rate: {max_throughput}")
    print(f"Maximum requests per second: {max_rps:.2f}")
    print(f"Final validation success rate: {stats['success_rate']*100:.4f}%")
    print(f"Final validation error rate: {(1-stats['success_rate'])*100:.4f}%")
    
    return max_throughput, max_rps

async def main():
    """Parse arguments and run tests"""
    parser = argparse.ArgumentParser(description="Load Testing for High School Activities API")
    parser.add_argument("--users", type=int, default=50, help="Number of concurrent users to simulate")
    parser.add_argument("--ramp-up", type=float, default=5.0, help="Ramp-up time in seconds")
    parser.add_argument("--find-max", action="store_true", help="Find maximum throughput that maintains SLA")
    args = parser.parse_args()
    
    if args.find_max:
        await find_maximum_throughput()
    else:
        await run_load_test(args.users, args.ramp_up)

if __name__ == "__main__":
    asyncio.run(main())