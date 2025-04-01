# High School Management System

## GitHub Actions Performance Testing

This repository includes GitHub Actions workflows to test the application's performance. You can run these tests both locally and on GitHub.

### Testing Locally

#### Prerequisites
- Python 3.10+
- Git
- [act](https://github.com/nektos/act) (for local GitHub Actions testing)

#### Option 1: Direct Testing
To run the performance tests directly on your local machine:

1. Clone the repository
   ```bash
   git clone <repository-url>
   cd skills-getting-started-with-github-copilot
   ```

2. Install dependencies
   ```bash
   pip install -r requirements.txt
   pip install pytest-html
   python -m playwright install chromium
   ```

3. Start the application
   ```bash
   python src/app.py > app.log 2>&1 &
   # Note the process ID for later cleanup
   echo $! > app.pid
   ```

4. Run performance tests
   ```bash
   mkdir -p reports
   python -m pytest src/performance_tests.py -v --html=reports/performance_report.html
   ```

5. Clean up
   ```bash
   kill $(cat app.pid)
   rm app.pid
   ```

#### Option 2: Using Act (GitHub Actions Local Testing)
If you have Docker installed, you can use `act` to run the GitHub Actions workflow locally:

1. Install act
   ```bash
   curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash
   ```

2. Run the local workflow
   ```bash
   ./bin/act -j run-performance-tests -W .github/workflows/local-performance-tests.yml --container-architecture linux/amd64
   ```

### Testing with GitHub Actions

The repository includes two GitHub Actions workflows:

1. `local-performance-tests.yml`: A simpler workflow that runs tests on GitHub-hosted runners
2. `azure-performance-tests.yml`: A comprehensive workflow that provisions an Azure VM and runs tests on it

#### Running on GitHub

To run the performance tests on GitHub:

1. Push your code to GitHub
   ```bash
   git push origin main
   ```

2. Go to "Actions" tab in your GitHub repository
3. Select "Azure Performance Tests" or "Local Performance Tests" workflow
4. Click "Run workflow" button
5. For Azure tests, you can customize:
   - Azure VM size (default: Standard_D2s_v3)
   - Azure region (default: eastus)

#### Setting up Azure Credentials

To run the Azure workflow, you need to set up Azure credentials as a repository secret:

1. Create an Azure Service Principal:
   ```bash
   az ad sp create-for-rbac --name "GithubActionsPerformanceTest" --role contributor \
                            --scopes /subscriptions/{subscription-id} \
                            --sdk-auth
   ```

2. Copy the JSON output
3. In your GitHub repository, go to Settings > Secrets > Actions
4. Create a new repository secret named `AZURE_CREDENTIALS` with the JSON output as the value

### Test Reports

After running tests, the workflow will:
1. Generate HTML test reports
2. Upload reports as artifacts
3. Generate a summary in the workflow run

You can download and view the test reports from the "Artifacts" section of the workflow run.

### Workflow Customization

You can customize both workflows by editing:
- `.github/workflows/local-performance-tests.yml` - For tests on GitHub runners
- `.github/workflows/azure-performance-tests.yml` - For tests on Azure VMs
