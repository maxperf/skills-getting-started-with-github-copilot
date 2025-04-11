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
import os
import sys
from datetime import datetime
from pathlib import Path

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

# Store load test results for export
LOAD_TEST_RESULTS = {
    "throughput": {},
    "sla": {},
    "system_info": {},
    "optimization": {}
}

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
        
        # Calculate percentiles
        sorted_times = sorted(response_times)
        p50_index = int(len(sorted_times) * 0.50)
        p95_index = int(len(sorted_times) * 0.95)
        p99_index = int(len(sorted_times) * 0.99)
        
        stats["endpoints"][endpoint] = {
            "requests": len(endpoint_results),
            "http_success_rate": http_success_count / len(endpoint_results) if endpoint_results else 0,
            "business_success_rate": combined_success_count / len(endpoint_results) if endpoint_results else 0,
            "error_count": error_count,
            "min_response_time": min(response_times) if response_times else 0,
            "max_response_time": max(response_times) if response_times else 0,
            "avg_response_time": statistics.mean(response_times) if response_times else 0,
            "p50_response_time": sorted_times[p50_index] if len(response_times) >= 2 else 0,
            "p95_response_time": sorted_times[p95_index] if len(response_times) >= 20 else 0,
            "p99_response_time": sorted_times[p99_index] if len(response_times) >= 100 else 0
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
        print(f"P50/P95/P99 response times: {data['p50_response_time']:.3f}s / {data['p95_response_time']:.3f}s / {data.get('p99_response_time', 'N/A')}")
        
        # Print some sample errors
        error_samples = [r.get("error") for r in endpoint_results if "error" in r][:3]
        if error_samples:
            print(f"Sample errors: {error_samples}")
    
    # Save results to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"load_test_results_{timestamp}.json"
    
    # Save to both the working directory and the reports directory if it exists
    with open(filename, "w") as f:
        json.dump(stats, f, indent=2)
    
    # Also save to the reports folder if it exists
    report_dir = Path("/workspaces/skills-getting-started-with-github-copilot/reports")
    if report_dir.exists():
        with open(report_dir / filename, "w") as f:
            json.dump(stats, f, indent=2)
    
    # Update the global results dictionary
    update_load_test_metrics(stats)
    
    print(f"\nDetailed results saved to: {filename}")
    
    return stats

def update_load_test_metrics(stats):
    """Update the global LOAD_TEST_RESULTS dictionary with the stats"""
    global LOAD_TEST_RESULTS
    
    # Update throughput metrics
    LOAD_TEST_RESULTS["throughput"]["requests_per_second"] = round(stats["requests_per_second"], 2)
    LOAD_TEST_RESULTS["throughput"]["concurrent_users"] = stats["concurrent_users"]
    LOAD_TEST_RESULTS["throughput"]["success_rate"] = round(stats["success_rate"], 4)
    
    # Calculate average values across all endpoints
    all_response_times = []
    all_success_rates = []
    
    for endpoint, data in stats["endpoints"].items():
        # Collect all response times
        endpoint_response_times = [data["avg_response_time"]]
        all_response_times.extend(endpoint_response_times)
        
        # Collect success rates
        all_success_rates.append(data["business_success_rate"])
        
        # Store details for this endpoint
        LOAD_TEST_RESULTS[f"endpoint_{endpoint}"] = {
            "avg_response_time": round(data["avg_response_time"], 3),
            "p95_response_time": round(data["p95_response_time"], 3),
            "p99_response_time": round(data.get("p99_response_time", 0), 3),
            "success_rate": round(data["business_success_rate"], 4)
        }
    
    # Update SLA metrics with average values
    LOAD_TEST_RESULTS["sla"]["avg_response_time"] = round(statistics.mean(all_response_times), 3) if all_response_times else 0
    LOAD_TEST_RESULTS["sla"]["error_rate"] = round(1 - statistics.mean(all_success_rates), 5) if all_success_rates else 0
    
    # Add test metadata
    LOAD_TEST_RESULTS["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOAD_TEST_RESULTS["duration"] = round(stats["test_duration"], 2)
    LOAD_TEST_RESULTS["total_requests"] = stats["total_requests"]

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
    optimal_concurrency = 0
    throughput_data = {}
    
    # First test various concurrency levels to find the optimal one that gives the highest throughput
    # with acceptable error rates
    print("\n--- Testing different concurrency levels to find optimal throughput ---")
    concurrency_levels = [5, 10, 20, 40, 60, 80, 100, 150, 200]
    
    for concurrency in concurrency_levels:
        print(f"\nTesting concurrency level: {concurrency} users")
        stats = await run_load_test(concurrency, ramp_up_time=3)
        success_rate = stats["success_rate"]
        rps = stats["requests_per_second"]
        
        throughput_data[concurrency] = {
            "success_rate": success_rate,
            "requests_per_second": rps,
            "error_rate": 1 - success_rate
        }
        
        print(f"Concurrency {concurrency}: {rps:.2f} RPS, {success_rate*100:.2f}% success rate")
        
        # Check if this is better than our current optimum while maintaining SLA
        if success_rate >= (1 - SLA_PARAMETERS["error_rate_threshold"]) and rps > max_rps:
            max_rps = rps
            optimal_concurrency = concurrency
        
        # If we're seeing high error rates, there's no need to test higher concurrency
        if success_rate < 0.90:  # 90% success rate threshold
            print(f"High error rate detected at concurrency {concurrency}. Stopping higher concurrency tests.")
            break
    
    # Once we've tested various concurrency levels, use binary search to fine-tune
    if optimal_concurrency > 0:
        print(f"\nOptimal concurrency level identified: {optimal_concurrency} users")
        print(f"Maximum throughput: {max_rps:.2f} requests/second")
        print(f"Success rate: {throughput_data[optimal_concurrency]['success_rate']*100:.2f}%")
        
        # Fine-tune around the optimal concurrency
        lower_bound = max(5, optimal_concurrency - 20)
        upper_bound = optimal_concurrency + 20
        
        # Binary search to find the precise optimal concurrency
        while upper_bound - lower_bound > 5:
            mid = (lower_bound + upper_bound) // 2
            print(f"\nFine-tuning: Testing {mid} users")
            
            stats = await run_load_test(mid, ramp_up_time=3)
            success_rate = stats["success_rate"]
            rps = stats["requests_per_second"]
            
            if success_rate >= (1 - SLA_PARAMETERS["error_rate_threshold"]):
                # This maintains SLA, so it's a potential candidate
                if rps > max_rps:
                    max_rps = rps
                    optimal_concurrency = mid
                
                # Still maintaining SLA, try higher
                lower_bound = mid
            else:
                # Not maintaining SLA, try lower
                upper_bound = mid
        
        max_throughput = optimal_concurrency
    else:
        print("\nNo concurrency level found that maintains SLA requirements.")
        # Use the best of what we have
        if throughput_data:
            best_concurrency = max(throughput_data.items(), key=lambda x: x[1]["requests_per_second"] * x[1]["success_rate"])[0]
            max_throughput = best_concurrency
            max_rps = throughput_data[best_concurrency]["requests_per_second"]
            optimal_concurrency = best_concurrency
    
    # Final validation test with the optimal concurrency
    print(f"\n--- Final validation with {max_throughput} users ---")
    final_stats = await run_load_test(max_throughput, ramp_up_time=5)
    
    print("\n====== MAXIMUM THROUGHPUT RESULTS ======")
    print(f"Maximum users while maintaining {(1-SLA_PARAMETERS['error_rate_threshold'])*100:.4f}% success rate: {max_throughput}")
    print(f"Maximum requests per second: {max_rps:.2f}")
    print(f"Final validation success rate: {final_stats['success_rate']*100:.4f}%")
    print(f"Final validation error rate: {(1-final_stats['success_rate'])*100:.4f}%")
    
    # Save the optimization results
    LOAD_TEST_RESULTS["optimization"] = {
        "optimal_concurrency": optimal_concurrency,
        "max_throughput_rps": round(max_rps, 2),
        "concurrency_tests": {
            str(k): {
                "success_rate": round(v["success_rate"], 4),
                "requests_per_second": round(v["requests_per_second"], 2),
                "error_rate": round(v["error_rate"], 4)
            } for k, v in throughput_data.items()
        }
    }
    
    # Save to performance_metrics.json for integration with the reports
    save_to_performance_metrics()
    
    return max_throughput, max_rps

def save_to_performance_metrics():
    """Save the load test results to the performance_metrics.json file to integrate with the reporting system"""
    global LOAD_TEST_RESULTS
    
    # Create the reports directory if it doesn't exist
    report_dir = Path("/workspaces/skills-getting-started-with-github-copilot/reports")
    report_dir.mkdir(exist_ok=True)
    
    # Path to the metrics file
    metrics_path = report_dir / "performance_metrics.json"
    
    # Load existing metrics if the file exists
    existing_metrics = {}
    if metrics_path.exists():
        try:
            with open(metrics_path, "r") as f:
                existing_metrics = json.load(f)
        except json.JSONDecodeError:
            print("Warning: Could not parse existing performance_metrics.json file. Creating a new one.")
    
    # Update with load test results
    existing_metrics.update({
        "load_test": LOAD_TEST_RESULTS,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    
    # If throughput data already exists in the metrics, merge it with our new data
    if "throughput" in existing_metrics and "optimization" in LOAD_TEST_RESULTS:
        existing_metrics["throughput"]["requests_per_second"] = LOAD_TEST_RESULTS["optimization"].get("max_throughput_rps", 
                                                                                                      existing_metrics["throughput"].get("requests_per_second", 0))
        existing_metrics["throughput"]["concurrent_users"] = LOAD_TEST_RESULTS["optimization"].get("optimal_concurrency", 
                                                                                                  existing_metrics["throughput"].get("concurrent_users", 0))
        if "concurrency_tests" in LOAD_TEST_RESULTS["optimization"]:
            existing_metrics["throughput"]["all_concurrency_tests"] = LOAD_TEST_RESULTS["optimization"]["concurrency_tests"]
    
    # Save updated metrics back to file
    with open(metrics_path, "w") as f:
        json.dump(existing_metrics, f, indent=2)
    
    print(f"\nLoad test results integrated into performance metrics: {metrics_path}")
    
    # Also generate a standalone HTML report for the load test
    generate_load_test_report(report_dir)

def generate_load_test_report(report_dir):
    """Generate an HTML report specifically for the load test results"""
    global LOAD_TEST_RESULTS
    
    html_path = report_dir / "load_test_summary.html"
    
    # Create a simple HTML report
    html_content = f'''
    <html>
    <head>
        <title>Load Test Results</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            h2, h3 {{ color: #333; }}
            .summary {{ background-color: #f8f8f8; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
            .passed {{ color: green; font-weight: bold; }}
            .failed {{ color: red; font-weight: bold; }}
            .chart-container {{ width: 100%; height: 400px; margin-bottom: 30px; }}
        </style>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body>
        <h1>Load Test Summary</h1>
        <div class='summary'>
            <p>Test run at: {LOAD_TEST_RESULTS.get("timestamp", "N/A")}</p>
            <p>Test duration: {LOAD_TEST_RESULTS.get("duration", "N/A")} seconds</p>
            <p>Total requests: {LOAD_TEST_RESULTS.get("total_requests", "N/A")}</p>
        </div>
        
        <h2>Throughput Results</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Optimal Concurrent Users</td><td>{LOAD_TEST_RESULTS.get("optimization", {}).get("optimal_concurrency", "N/A")}</td></tr>
            <tr><td>Maximum Throughput (RPS)</td><td>{LOAD_TEST_RESULTS.get("optimization", {}).get("max_throughput_rps", "N/A")}</td></tr>
            <tr><td>Success Rate at Max Throughput</td><td>{LOAD_TEST_RESULTS.get("throughput", {}).get("success_rate", "N/A") * 100:.2f}%</td></tr>
            <tr><td>Error Rate at Max Throughput</td><td>{(1 - LOAD_TEST_RESULTS.get("throughput", {}).get("success_rate", 0)) * 100:.2f}%</td></tr>
        </table>
        
        <h2>Concurrency Test Results</h2>
        <div class="chart-container">
            <canvas id="throughputChart"></canvas>
        </div>
        
        <table>
            <tr><th>Concurrency</th><th>RPS</th><th>Success Rate</th><th>Error Rate</th></tr>
            {
                ''.join([
                    f"<tr><td>{c}</td><td>{data['requests_per_second']}</td><td>{data['success_rate']*100:.2f}%</td><td>{data['error_rate']*100:.2f}%</td></tr>"
                    for c, data in sorted(LOAD_TEST_RESULTS.get("optimization", {}).get("concurrency_tests", {}).items(), key=lambda x: int(x[0]))
                ])
            }
        </table>
        
        <h2>SLA Metrics</h2>
        <table>
            <tr><th>Metric</th><th>Value</th><th>SLA Target</th><th>Status</th></tr>
            <tr>
                <td>Average Response Time</td>
                <td>{LOAD_TEST_RESULTS.get("sla", {}).get("avg_response_time", "N/A")} seconds</td>
                <td>{SLA_PARAMETERS["response_time_threshold"]} seconds</td>
                <td class="{'passed' if LOAD_TEST_RESULTS.get('sla', {}).get('avg_response_time', 999) < SLA_PARAMETERS['response_time_threshold'] else 'failed'}">
                    {"PASSED" if LOAD_TEST_RESULTS.get('sla', {}).get('avg_response_time', 999) < SLA_PARAMETERS['response_time_threshold'] else "FAILED"}
                </td>
            </tr>
            <tr>
                <td>Error Rate</td>
                <td>{LOAD_TEST_RESULTS.get("sla", {}).get("error_rate", "N/A") * 100:.3f}%</td>
                <td>{SLA_PARAMETERS["error_rate_threshold"] * 100:.3f}%</td>
                <td class="{'passed' if LOAD_TEST_RESULTS.get('sla', {}).get('error_rate', 999) <= SLA_PARAMETERS['error_rate_threshold'] else 'failed'}">
                    {"PASSED" if LOAD_TEST_RESULTS.get('sla', {}).get('error_rate', 999) <= SLA_PARAMETERS['error_rate_threshold'] else "FAILED"}
                </td>
            </tr>
        </table>
        
        <script>
            // Extract data for charts
            const concurrencyLevels = [
                {', '.join([c for c in sorted(LOAD_TEST_RESULTS.get("optimization", {}).get("concurrency_tests", {}).keys(), key=int)])}
            ];
            const rpsValues = [
                {', '.join([str(data['requests_per_second']) for c, data in sorted(LOAD_TEST_RESULTS.get("optimization", {}).get("concurrency_tests", {}).items(), key=lambda x: int(x[0]))])}
            ];
            const successRates = [
                {', '.join([str(data['success_rate']*100) for c, data in sorted(LOAD_TEST_RESULTS.get("optimization", {}).get("concurrency_tests", {}).items(), key=lambda x: int(x[0]))])}
            ];
            
            // Create throughput chart
            const throughputCtx = document.getElementById('throughputChart').getContext('2d');
            new Chart(throughputCtx, {{
                type: 'line',
                data: {{
                    labels: concurrencyLevels,
                    datasets: [
                        {{
                            label: 'Requests per Second',
                            borderColor: 'rgb(54, 162, 235)',
                            backgroundColor: 'rgba(54, 162, 235, 0.1)',
                            yAxisID: 'y',
                            data: rpsValues,
                            tension: 0.1
                        }},
                        {{
                            label: 'Success Rate (%)',
                            borderColor: 'rgb(75, 192, 192)',
                            backgroundColor: 'rgba(75, 192, 192, 0.1)',
                            yAxisID: 'y1',
                            data: successRates,
                            tension: 0.1
                        }}
                    ]
                }},
                options: {{
                    responsive: true,
                    interaction: {{
                        mode: 'index',
                        intersect: false,
                    }},
                    stacked: false,
                    scales: {{
                        y: {{
                            type: 'linear',
                            display: true,
                            position: 'left',
                            title: {{
                                display: true,
                                text: 'Requests per Second'
                            }}
                        }},
                        y1: {{
                            type: 'linear',
                            display: true,
                            position: 'right',
                            title: {{
                                display: true,
                                text: 'Success Rate (%)'
                            }},
                            min: 0,
                            max: 100,
                            grid: {{
                                drawOnChartArea: false,
                            }}
                        }}
                    }}
                }}
            }});
        </script>
    </body>
    </html>
    '''
    
    with open(html_path, "w") as f:
        f.write(html_content)
    
    print(f"Load test report generated at: {html_path}")

async def main():
    """Parse arguments and run tests"""
    parser = argparse.ArgumentParser(description="Load Testing for High School Activities API")
    parser.add_argument("--users", type=int, default=50, help="Number of concurrent users to simulate")
    parser.add_argument("--ramp-up", type=float, default=5.0, help="Ramp-up time in seconds")
    parser.add_argument("--find-max", action="store_true", help="Find maximum throughput that maintains SLA")
    parser.add_argument("--optimize", action="store_true", help="Optimize for throughput with the lowest fail rate")
    args = parser.parse_args()
    
    if args.find_max or args.optimize:
        await find_maximum_throughput()
    else:
        stats = await run_load_test(args.users, args.ramp_up)
        save_to_performance_metrics()

if __name__ == "__main__":
    asyncio.run(main())