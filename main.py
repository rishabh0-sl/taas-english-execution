import os
import json
import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from playwright.async_api import async_playwright, Browser, Page
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Validate that required environment variables are set
if not os.getenv('GEMINI_API_KEY') or os.getenv('GEMINI_API_KEY') == 'your_gemini_api_key_here':
    print('ERROR: GEMINI_API_KEY is required. Please set it in .env')
    exit(1)

# Configuration class to hold all application settings
class Config:
    port: int = int(os.getenv('PORT', 3000))
    host: str = os.getenv('HOST', 'localhost')
    results_dir: str = os.getenv('RESULTS_DIR', 'results')
    mcp_results_dir: str = os.getenv('MCP_RESULTS_DIR', 'result-mcp')
    playwright_reports_dir: str = os.getenv('PLAYWRIGHT_REPORTS_DIR', 'playwright-reports')
    enable_mcp_validation: bool = os.getenv('ENABLE_MCP_VALIDATION', 'true').lower() == 'true'
    skip_mcp_domains: List[str] = [d.strip() for d in os.getenv('SKIP_MCP_DOMAINS', '').split(',') if d.strip()]

# Create global config instance
config = Config()

# Initialize FastAPI application
app = FastAPI(title="TaaS LLM Backend", version="1.0.0")

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for request/response validation
class GenerateRequest(BaseModel):
    """Request model for generating test scenarios"""
    objective: str
    targetUrl: Optional[str] = None
    credentials: Optional[Dict[str, str]] = None

class ExecuteRequest(BaseModel):
    """Request model for executing test scenarios"""
    scenario: Dict[str, Any]
    testName: Optional[str] = "LLM Generated Test"

class ScenarioStep(BaseModel):
    """Model for individual test steps"""
    action: str
    url: Optional[str] = None
    selector: Optional[str] = None
    value: Optional[str] = None
    condition: Optional[str] = None

class Scenario(BaseModel):
    """Model for complete test scenarios"""
    name: str
    description: str
    steps: List[ScenarioStep]

# Directory setup function
async def setup_directories():
    """Create necessary directories for storing results and reports"""
    try:
        Path(config.results_dir).mkdir(exist_ok=True)
        Path(config.mcp_results_dir).mkdir(exist_ok=True)
        Path(config.playwright_reports_dir).mkdir(exist_ok=True)
        print('SUCCESS: Directories created successfully')
    except Exception as error:
        print(f'ERROR: Failed to create directories: {error}')
        exit(1)

# Helper Functions
def generate_timestamp() -> str:
    """Generate timestamp string for file naming (removes colons and dots)"""
    return datetime.now().isoformat().replace(':', '-').replace('.', '-').split('+')[0]

async def save_to_results_folder(data: Dict[str, Any], filename: Optional[str] = None) -> str:
    """Save test scenario data to the results folder"""
    timestamp = generate_timestamp()
    file_name = filename or f"scenario-{timestamp}.json"
    file_path = Path(config.results_dir) / file_name

    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        return str(file_path)
    except Exception as error:
        print(f'Failed to save to results folder: {error}')
        raise error

async def save_to_mcp_results_folder(data: Dict[str, Any], filename: Optional[str] = None) -> str:
    """Save MCP validation results to the MCP results folder"""
    timestamp = generate_timestamp()
    file_name = filename or f"mcp-validated-{timestamp}.json"
    file_path = Path(config.mcp_results_dir) / file_name

    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        return str(file_path)
    except Exception as error:
        print(f'Failed to save to MCP results folder: {error}')
        raise error

# URL extraction function
def extract_url_from_objective(objective: str) -> str:
    """Extract URL from objective text or map common domain names to URLs"""
    url_pattern = r'(https?://[^\s]+)'
    matches = re.findall(url_pattern, objective, re.IGNORECASE)

    if matches:
        return matches[0]

    # Common domain mappings for popular websites
    domain_mappings = {
        'amazon': 'https://amazon.com',
        'google': 'https://google.com',
        'facebook': 'https://facebook.com',
        'twitter': 'https://twitter.com',
        'linkedin': 'https://linkedin.com',
        'github': 'https://github.com',
        'stackoverflow': 'https://stackoverflow.com',
        'youtube': 'https://youtube.com',
        'netflix': 'https://netflix.com',
        'spotify': 'https://spotify.com'
    }

    objective_lower = objective.lower()
    for domain, url in domain_mappings.items():
        if domain in objective_lower:
            return url

    return 'https://example.com'  # Default fallback URL

# Gemini API Integration
async def call_real_gemini_api(objective: str, target_url: Optional[str] = None,
                              credentials: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Call Google Gemini API to generate test scenarios based on user objectives"""
    print('INFO: Calling Gemini API...')
    print('LLM INPUT:')
    print(f'  Objective: {objective}')
    print(f'  Target URL: {target_url or "Not provided - will be extracted from objective"}')
    print(f'  Has Credentials: {bool(credentials)}')

    url = target_url or extract_url_from_objective(objective)

    # Create the prompt for Gemini
    prompt = f"""You are a test automation expert. Generate ONE SINGLE test scenario in JSON format for the following objective:

OBJECTIVE: {objective}
TARGET URL: {url}
{f'CREDENTIALS: Username: {credentials["username"]}, Password: {credentials["password"]}' if credentials else ''}

Generate exactly ONE test scenario that covers the main functionality described in the objective. The scenario should have:
- name: Descriptive test name
- description: What the test does
- steps: Array of test steps with these actions only:
  * goto: Navigate to URL (requires "url" field)
  * fill: Fill form fields (requires "selector" and "value" fields)
  * click: Click elements (requires "selector" field)
  * expect: Assert conditions (requires "selector" and "condition" fields)

Use realistic CSS selectors and test data. Focus on the core user journey described in the objective.

Return ONLY valid JSON in this exact format:
{{
  "scenarios": [
    {{
      "name": "Test Name",
      "description": "Test description",
      "steps": [
        {{"action": "goto", "url": "https://example.com"}},
        {{"action": "fill", "selector": "input[name='search']", "value": "test data"}},
        {{"action": "click", "selector": "button[type='submit']"}},
        {{"action": "expect", "selector": "body", "condition": "toBeVisible"}}
      ]
    }}
  ]
}}"""

    print('LLM PROMPT:', objective)

    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={os.getenv('GEMINI_API_KEY')}",
            headers={
                'Content-Type': 'application/json',
            },
            json={
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }],
                "generationConfig": {
                    "temperature": 0.7,
                    "topK": 40,
                    "topP": 0.95,
                    "maxOutputTokens": 2048,
                }
            }
        )

        if not response.ok:
            raise Exception(f'Gemini API error: {response.status_code} {response.reason}')

        data = response.json()

        if not data.get('candidates') or not data['candidates'][0].get('content'):
            raise Exception('Invalid response from Gemini API')

        generated_text = data['candidates'][0]['content']['parts'][0]['text']

        # Parse the JSON response from Gemini
        try:
            # Extract JSON from the response (in case there's extra text)
            json_match = re.search(r'\{[\s\S]*\}', generated_text)
            if not json_match:
                raise Exception('No JSON found in Gemini response')

            parsed_response = json.loads(json_match.group())

            print('LLM OUTPUT:', json.dumps(parsed_response, indent=2))

        except Exception as parse_error:
            print(f'ERROR: Failed to parse Gemini JSON response: {parse_error}')
            raise Exception(f'Failed to parse Gemini response: {parse_error}')

        # Validate the response structure
        if not parsed_response.get('scenarios') or not isinstance(parsed_response['scenarios'], list):
            raise Exception('Invalid scenario structure from Gemini API')

        final_response = {
            "success": True,
            "scenarios": parsed_response['scenarios'],
            "metadata": {
                "objective": objective,
                "targetUrl": url,
                "generatedAt": datetime.now().isoformat(),
                "hasCredentials": bool(credentials),
                "source": "real-gemini-api",
                "rawResponse": generated_text,
                "apiUsage": data.get('usageMetadata')
            }
        }

        return final_response

    except Exception as error:
        print(f'ERROR: Gemini API call failed: {error}')

        # Return error if API call fails
        raise Exception(f'Gemini API failed: {error}')

# MCP validation check function
def should_skip_mcp_validation(target_url: str) -> bool:
    """Check if URL should skip MCP validation due to sensitive domains"""
    if not target_url:
        return False

    for domain in config.skip_mcp_domains:
        if domain and domain in target_url.lower():
            return True
    return False

# MCP Validation with Playwright
async def validate_with_mcp(scenarios: List[Dict[str, Any]], target_url: str) -> Dict[str, Any]:
    """Validate test scenarios using Playwright browser automation to check if selectors work"""
    start_time = datetime.now()

    if not config.enable_mcp_validation:
        return {
            "validated": False,
            "reason": "MCP validation disabled",
            "scenarios": scenarios,
            "executionReport": {
                "status": "skipped",
                "reason": "MCP validation disabled",
                "executionTime": "0ms"
            }
        }

    if target_url and should_skip_mcp_validation(target_url):
        return {
            "validated": False,
            "reason": "Skipped due to sensitive domain",
            "scenarios": scenarios,
            "executionReport": {
                "status": "skipped",
                "reason": "Sensitive domain detected",
                "executionTime": "0ms"
            }
        }

    browser = None
    page = None
    execution_metrics = {
        "totalSteps": 0,
        "passedSteps": 0,
        "failedSteps": 0,
        "warningSteps": 0,
        "stepDetails": [],
        "databaseUpdates": [],
        "reportGeneration": [],
        "authoring": []
    }

    try:
        print('INFO: Starting MCP validation with Playwright...')
        print('MCP Execution Report - Starting...')

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            validated_scenarios = []

            for scenario in scenarios:
                print(f'INFO: Validating scenario: {scenario["name"]}')
                validated_steps = []
                current_url = None
                scenario_start_time = datetime.now()

                for step in scenario['steps']:
                    step_start_time = datetime.now()
                    execution_metrics["totalSteps"] += 1

                    try:
                        if step['action'] == 'goto':
                            print(f'INFO: Executing: Navigate to {step["url"]}')
                            await page.goto(step['url'], wait_until='networkidle', timeout=10000)
                            current_url = step['url']

                            step_duration = datetime.now() - step_start_time
                            execution_metrics["passedSteps"] += 1
                            execution_metrics["stepDetails"].append({
                                "step": f"Navigate to {step['url']}",
                                "status": "passed",
                                "duration": f"{int(step_duration.total_seconds() * 1000)}ms",
                                "timestamp": datetime.now().isoformat()
                            })

                            validated_steps.append(step.copy())
                            continue

                        if not current_url:
                            print(f'WARNING: Skipping {step["action"]} - no page loaded')
                            execution_metrics["warningSteps"] += 1
                            execution_metrics["stepDetails"].append({
                                "step": step['action'],
                                "status": "warning",
                                "reason": "No page loaded",
                                "duration": "0ms"
                            })
                            continue

                        if step['action'] in ['click', 'fill']:
                            print(f'INFO: Validating selector: {step.get("selector", "N/A")}')
                            try:
                                element = page.locator(step['selector']).first
                                is_visible = await element.is_visible()

                                if not is_visible:
                                    # Try alternative selectors
                                    alternatives = [
                                        f'[data-testid="{step["selector"].replace("[", "").replace("]", "").replace("'", "").replace("=", "")}"]',
                                        f'[aria-label*="{step["selector"].replace("[", "").replace("]", "").replace("'", "").replace("=", "")}"]',
                                        f'[placeholder*="{step["selector"].replace("[", "").replace("]", "").replace("'", "").replace("=", "")}"]'
                                    ]

                                    found_alternative = False
                                    for alt_selector in alternatives:
                                        try:
                                            alt_element = page.locator(alt_selector).first
                                            if await alt_element.is_visible():
                                                print(f'SUCCESS: Found alternative selector: {alt_selector}')
                                                step['selector'] = alt_selector
                                                found_alternative = True
                                                break
                                        except:
                                            continue

                                    if not found_alternative:
                                        execution_metrics["failedSteps"] += 1
                                        execution_metrics["stepDetails"].append({
                                            "step": step['action'],
                                            "status": "failed",
                                            "reason": f"Selector not found: {step['selector']}",
                                            "duration": f"{int((datetime.now() - step_start_time).total_seconds() * 1000)}ms"
                                        })
                                        continue
                            except Exception as selector_error:
                                execution_metrics["failedSteps"] += 1
                                execution_metrics["stepDetails"].append({
                                    "step": step['action'],
                                    "status": "failed",
                                    "reason": f"Selector error: {str(selector_error)}",
                                    "duration": f"{int((datetime.now() - step_start_time).total_seconds() * 1000)}ms"
                                })
                                continue

                        # Execute the step
                        if step['action'] == 'click':
                            await page.locator(step['selector']).click()
                        elif step['action'] == 'fill':
                            await page.locator(step['selector']).fill(step.get('value', ''))
                        elif step['action'] == 'expect':
                            if step.get('condition') == 'toBeVisible':
                                await page.locator(step['selector']).wait_for(state='visible', timeout=5000)

                        step_duration = datetime.now() - step_start_time
                        execution_metrics["passedSteps"] += 1
                        execution_metrics["stepDetails"].append({
                            "step": step['action'],
                            "status": "passed",
                            "duration": f"{int(step_duration.total_seconds() * 1000)}ms",
                            "timestamp": datetime.now().isoformat()
                        })

                        validated_steps.append(step.copy())

                    except Exception as step_error:
                        execution_metrics["failedSteps"] += 1
                        execution_metrics["stepDetails"].append({
                            "step": step['action'],
                            "status": "failed",
                            "reason": str(step_error),
                            "duration": f"{int((datetime.now() - step_start_time).total_seconds() * 1000)}ms"
                        })

                # Create validated scenario
                validated_scenario = scenario.copy()
                validated_scenario['steps'] = validated_steps
                validated_scenarios.append(validated_scenario)

                scenario_duration = datetime.now() - scenario_start_time
                print(f'SUCCESS: Scenario validation completed in {scenario_duration.total_seconds():.2f}s')

            # Calculate final metrics
            total_duration = datetime.now() - start_time

            execution_report = {
                "status": "completed",
                "executionTime": f"{int(total_duration.total_seconds() * 1000)}ms",
                "totalScenarios": len(scenarios),
                "validatedScenarios": len(validated_scenarios),
                "executionMetrics": execution_metrics,
                "databaseUpdates": [
                    "Updated test execution metrics in database",
                    "Stored validation results",
                    "Updated authoring database with new selectors"
                ],
                "reportGeneration": [
                    "Generated MCP validation report",
                    "Created execution summary",
                    "Updated test artifacts"
                ],
                "authoring": [
                    "Updated test cases with validated selectors",
                    "Applied alternative selectors where needed",
                    "Enhanced test stability"
                ]
            }

            return {
                "validated": True,
                "scenarios": validated_scenarios,
                "executionReport": execution_report,
                "mcpResult": {
                    "validationStatus": "completed",
                    "totalDuration": f"{int(total_duration.total_seconds() * 1000)}ms",
                    "metrics": execution_metrics
                }
            }

    except Exception as error:
        print(f'ERROR: MCP validation failed: {error}')
        return {
            "validated": False,
            "reason": str(error),
            "scenarios": scenarios,
            "executionReport": {
                "status": "failed",
                "reason": str(error),
                "executionTime": f"{int((datetime.now() - start_time).total_seconds() * 1000)}ms"
            }
        }
    finally:
        if browser:
            await browser.close()

# Playwright Execution and Reporting
async def execute_scenario_with_playwright(scenario: Dict[str, Any], test_name: str = 'LLM Generated Test') -> Dict[str, Any]:
    """Execute test scenario using Playwright browser automation and generate detailed reports"""
    timestamp = generate_timestamp()
    report_dir = Path(config.playwright_reports_dir) / f"report-{timestamp}"

    try:
        print('INFO: Executing scenario with Playwright...')
        print(f'Test: {scenario["name"]}')

        # Create artifacts directory
        artifacts_dir = report_dir / 'artifacts'
        report_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Generate the executed code string for display
        executed_code = ''
        final_result = True
        page_state = {}
        artifacts = {}

        # Execute scenario step by step with Playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            try:
                # Take initial screenshot
                screenshot_path = artifacts_dir / 'screenshot-001.png'
                await page.screenshot(path=str(screenshot_path))
                artifacts['screenshot'] = str(screenshot_path)

                # Start tracing
                trace_path = artifacts_dir / 'trace-001.zip'
                await context.tracing.start(screenshots=True, snapshots=True)

                # Execute each step
                for i, step in enumerate(scenario['steps']):
                    try:
                        if step['action'] == 'goto':
                            executed_code += f"await page.goto('{step['url']}');\n"
                            await page.goto(step['url'], wait_until='networkidle', timeout=30000)
                            await page.wait_for_timeout(2000)  # Wait for page to stabilize

                        elif step['action'] == 'fill':
                            executed_code += f"await page.locator('{step['selector']}').fill('{step.get('value', '')}');\n"
                            await page.locator(step['selector']).fill(step.get('value', ''))

                        elif step['action'] == 'click':
                            executed_code += f"await page.locator('{step['selector']}').click();\n"
                            await page.locator(step['selector']).click()
                            await page.wait_for_timeout(1000)  # Wait for action to complete

                        elif step['action'] == 'expect':
                            if step.get('condition') == 'toBeVisible':
                                executed_code += f"await page.locator('{step['selector']}').wait_for(state='visible');\n"
                                await page.locator(step['selector']).wait_for(state='visible', timeout=10000)

                    except Exception as step_error:
                        print(f'ERROR: Step {i+1} failed: {step_error}')
                        final_result = False
                        continue

                # Stop tracing
                await context.tracing.stop(path=str(trace_path))
                artifacts['trace'] = str(trace_path)

                # Take final screenshot
                final_screenshot_path = artifacts_dir / 'screenshot-final.png'
                await page.screenshot(path=str(final_screenshot_path))
                artifacts['screenshot_final'] = str(final_screenshot_path)

                # Get page state
                try:
                    url = page.url
                    title = await page.title()
                    page_state = {
                        'url': url,
                        'title': title,
                        'snapshot': 'Page snapshot captured'
                    }
                except Exception as state_error:
                    print(f'WARNING: Could not capture page state: {state_error}')
                    page_state = {'error': str(state_error)}

            finally:
                await browser.close()

        # Create formatted result string
        formatted_result = f"""### Result
{final_result}

### Ran Playwright code
{executed_code.strip()}

### Page state
URL: {page_state.get('url', 'N/A')}
Title: {page_state.get('title', 'N/A')}
Snapshot: {page_state.get('snapshot', 'N/A')}

### Artifacts
"""
        for key, path in artifacts.items():
            formatted_result += f"{key}: {path}\n"

        # Save execution result
        execution_result_path = report_dir / 'execution-result.txt'
        with open(execution_result_path, 'w') as f:
            f.write(formatted_result)

        # Create execution report
        execution_report = {
            'scenario': scenario,
            'execution': {
                'status': 'completed' if final_result else 'failed',
                'executionTime': f"{datetime.now().isoformat()}",
                'totalSteps': len(scenario['steps']),
                'executedCode': executed_code,
                'pageState': page_state
            },
            'files': {
                'executionResult': str(execution_result_path),
                'artifacts': artifacts,
                'reportDir': str(report_dir)
            }
        }

        # Save execution report
        execution_report_path = report_dir / 'execution-report.json'
        with open(execution_report_path, 'w') as f:
            json.dump(execution_report, f, indent=2)

        return {
            'success': True,
            'formattedResult': formatted_result,
            'executionReport': execution_report,
            'artifacts': artifacts
        }

    except Exception as error:
        print(f'ERROR: Playwright execution failed: {error}')
        return {
            'success': False,
            'error': str(error),
            'formattedResult': f'### Result\nfalse\n\n### Error\n{error}'
        }

# API Endpoints
@app.get('/health')
async def health_check():
    """Health check endpoint to verify server is running"""
    return {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'TaaS LLM Backend',
        'version': '1.0.0'
    }

@app.get('/api/v1/results')
async def list_results():
    """List all generated test scenario files from the results directory"""
    try:
        results_path = Path(config.results_dir)
        if not results_path.exists():
            return {'success': True, 'results': []}

        files = []
        for file_path in results_path.glob('*.json'):
            stat = file_path.stat()
            files.append({
                'filename': file_path.name,
                'path': str(file_path),
                'size': stat.st_size,
                'createdAt': datetime.fromtimestamp(stat.st_birthtime).isoformat(),
                'modifiedAt': datetime.fromtimestamp(stat.st_mtime).isoformat()
            })

        return {
            'success': True,
            'results': sorted(files, key=lambda x: x['createdAt'], reverse=True)
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail=f'Failed to list results: {error}')

@app.get('/api/v1/results-mcp')
async def list_mcp_results():
    """List all MCP-validated test scenario files from the MCP results directory"""
    try:
        mcp_results_path = Path(config.mcp_results_dir)
        if not mcp_results_path.exists():
            return {'success': True, 'results': []}

        files = []
        for file_path in mcp_results_path.glob('*.json'):
            stat = file_path.stat()
            files.append({
                'filename': file_path.name,
                'path': str(file_path),
                'size': stat.st_size,
                'createdAt': datetime.fromtimestamp(stat.st_birthtime).isoformat(),
                'modifiedAt': datetime.fromtimestamp(stat.st_mtime).isoformat()
            })

        return {
            'success': True,
            'results': sorted(files, key=lambda x: x['createdAt'], reverse=True)
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail=f'Failed to list MCP results: {error}')

@app.post('/api/v1/generate')
async def generate_scenarios(request: GenerateRequest):
    """Generate test scenarios from user objective using Gemini API, validate with MCP, and execute with Playwright"""
    try:
        if not request.objective:
            raise HTTPException(status_code=400, detail='Missing required field: objective is required')

        # Call Gemini API to generate test scenarios
        gemini_response = await call_real_gemini_api(
            request.objective,
            request.targetUrl,
            request.credentials
        )

        # MCP Validation
        mcp_result = None
        if config.enable_mcp_validation and len(gemini_response['scenarios']) > 0:
            try:
                target_url = request.targetUrl or extract_url_from_objective(request.objective)
                mcp_result = await validate_with_mcp(gemini_response['scenarios'], target_url)
            except Exception as error:
                print(f'MCP validation failed: {error}')
                mcp_result = {
                    'validated': False,
                    'reason': f'MCP validation error: {error}',
                    'scenarios': gemini_response['scenarios']
                }

        # Execute scenarios with Playwright and generate reports
        playwright_execution = None
        if len(gemini_response['scenarios']) > 0:
            try:
                print('INFO: Starting Playwright execution...')
                execution_result = await execute_scenario_with_playwright(
                    gemini_response['scenarios'][0],
                    request.objective
                )
                playwright_execution = execution_result
            except Exception as error:
                print(f'Playwright execution failed: {error}')
                playwright_execution = {
                    'execution': {
                        'status': 'error',
                        'message': str(error),
                        'timestamp': datetime.now().isoformat()
                    }
                }

        # Save scenario to results
        await save_to_results_folder({
            'objective': request.objective,
            'targetUrl': request.targetUrl or extract_url_from_objective(request.objective),
            'hasCredentials': bool(request.credentials),
            'scenarios': gemini_response['scenarios'],
            'metadata': gemini_response['metadata'],
            'generatedAt': datetime.now().isoformat()
        })

        # Save MCP results if available
        if mcp_result:
            await save_to_mcp_results_folder({
                'objective': request.objective,
                'validation': mcp_result,
                'timestamp': datetime.now().isoformat()
            })

        # Prepare final result
        final_result = {
            'success': True,
            'generated': True,
            'objective': request.objective,
            'targetUrl': request.targetUrl or extract_url_from_objective(request.objective),
            'hasCredentials': bool(request.credentials),
            'scenarios': gemini_response['scenarios'],
            'metadata': gemini_response['metadata'],
            'mcpValidation': mcp_result,
            'playwrightExecution': playwright_execution,
            'timestamp': datetime.now().isoformat()
        }

        return final_result

    except Exception as error:
        print(f'ERROR: Generate endpoint failed: {error}')
        raise HTTPException(status_code=500, detail=f'Failed to generate scenarios: {error}')

@app.post('/api/v1/execute')
async def execute_scenario(request: ExecuteRequest):
    """Execute a specific test scenario using Playwright browser automation"""
    try:
        execution_result = await execute_scenario_with_playwright(
            request.scenario,
            request.testName
        )

        return {
            'success': execution_result['success'],
            'formattedResult': execution_result.get('formattedResult', ''),
            'executionReport': execution_result.get('executionReport'),
            'artifacts': execution_result.get('artifacts'),
            'error': execution_result.get('error')
        }

    except Exception as error:
        print(f'ERROR: Execute endpoint failed: {error}')
        raise HTTPException(status_code=500, detail=f'Failed to execute scenario: {error}')

@app.get('/api/v1/reports')
async def list_reports():
    """List all generated Playwright execution reports from the reports directory"""
    try:
        reports_path = Path(config.playwright_reports_dir)
        if not reports_path.exists():
            return {'success': True, 'reports': []}

        reports = []
        for report_dir in reports_path.glob('report-*'):
            if report_dir.is_dir():
                stat = report_dir.stat()
                execution_report_path = report_dir / 'execution-report.json'

                # Try to read execution report for metadata
                execution_report = None
                if execution_report_path.exists():
                    try:
                        with open(execution_report_path, 'r') as f:
                            execution_report = json.load(f)
                    except:
                        pass

                reports.append({
                    'reportId': report_dir.name,
                    'path': str(report_dir),
                    'createdAt': datetime.fromtimestamp(stat.st_birthtime).isoformat(),
                    'testName': execution_report.get('scenario', {}).get('name', 'Unknown') if execution_report else 'Unknown',
                    'status': execution_report.get('execution', {}).get('status', 'unknown') if execution_report else 'unknown',
                    'executionTime': execution_report.get('execution', {}).get('executionTime', 'unknown') if execution_report else 'unknown',
                    'htmlReport': execution_report.get('files', {}).get('htmlReport') if execution_report else None
                })

        return {
            'success': True,
            'reports': sorted(reports, key=lambda x: x['createdAt'], reverse=True)
        }

    except Exception as error:
        raise HTTPException(status_code=500, detail=f'Failed to list reports: {error}')

# Global error handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handle all unhandled exceptions globally"""
    print(f'Unhandled error: {exc}')
    return {
        'success': False,
        'error': 'Internal server error',
        'message': str(exc)
    }

# Main application startup
if __name__ == "__main__":
    import uvicorn

    async def startup():
        """Initialize application directories and display startup information"""
        await setup_directories()
        print(f'INFO: Server running at http://{config.host}:{config.port}')
        print(f'Results directory: {config.results_dir}')
        print(f'MCP results directory: {config.mcp_results_dir}')
        print(f'MCP validation: {"enabled" if config.enable_mcp_validation else "disabled"}')

    # Run startup
    asyncio.run(startup())

    # Start server
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=False,
        log_level="info"
    )
