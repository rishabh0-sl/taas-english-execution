# Playwright Test Generator

A Node.js backend service that converts plain English instructions into executable Playwright test scripts using the Gemini API.

## Features

- 🚀 **Fastify-based REST API** - High-performance web framework
- 🤖 **Gemini AI Integration** - Converts natural language to Playwright code
- 🎭 **Playwright Test Generation** - Creates executable test scripts
- 📁 **Automatic File Management** - Saves and organizes generated tests
- ✅ **Code Validation** - Validates generated code before execution
- 🏃 **Test Execution** - Optional automatic test execution
- 📊 **Comprehensive Logging** - Detailed logs for debugging

## Quick Start

### Prerequisites

- Node.js 18+ 
- npm or yarn
- Google Gemini API key

### Installation

1. **Clone or download the project**
   ```bash
   cd playwright-test-generator
   ```

2. **Install dependencies**
   ```bash
   npm install
   ```

3. **Set up environment variables**
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` file and add your Gemini API key:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   GEMINI_MODEL=gemini-1.5-flash
   PORT=3000
   ```

4. **Start the server**
   ```bash
   npm start
   ```

   The server will start on `http://localhost:3000`

### Usage

#### Generate a Playwright Test

Send a POST request to `/api/generate-test`:

```bash
curl -X POST http://localhost:3000/api/generate-test \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "Go to amazon.in, search for shoes for men, click on the first product",
    "testName": "amazon-shoes-test",
    "executeTest": false
  }'
```

**Response:**
```json
{
  "success": true,
  "playwrightCode": "const { test, expect } = require('@playwright/test');\n\ntest('amazon shoes test', async ({ page }) => {\n  // Navigate to Amazon India\n  await page.goto('https://amazon.in');\n  \n  // Search for men's shoes\n  await page.fill('input[name=\"field-keywords\"]', 'shoes for men');\n  await page.click('input[type=\"submit\"]');\n  \n  // Click on the first product\n  await page.click('.s-result-item:first-child h2 a');\n  \n  // Verify we're on a product page\n  await expect(page).toHaveURL(/\\/dp\\//);\n});",
  "testFilePath": "/path/to/tests/amazon-shoes-test-1234567890.spec.js",
  "validation": {
    "isValid": true,
    "errors": [],
    "warnings": []
  },
  "timestamp": "2024-01-15T10:30:00.000Z"
}
```

#### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/generate-test` | Generate Playwright test from instruction |
| `GET` | `/api/tests` | List all generated test files |
| `POST` | `/api/execute-test` | Execute a specific test file |
| `GET` | `/api/health` | Check service health |
| `GET` | `/health` | Basic health check |

#### Request Parameters

**POST /api/generate-test**
- `instruction` (required): Plain English instruction (10-1000 characters)
- `testName` (optional): Name for the test file
- `executeTest` (optional): Whether to execute the test immediately (default: false)

**POST /api/execute-test**
- `testFileName` (required): Name of the test file to execute

### Running Generated Tests

Generated tests are saved in the `tests/` directory and can be run using:

```bash
# Run all tests
npx playwright test

# Run a specific test
npx playwright test tests/your-test-name.spec.js

# Run with UI mode
npx playwright test --ui

# Run in headed mode (see browser)
npx playwright test --headed
```

### Project Structure

```
playwright-test-generator/
├── server.js                 # Main server entry point
├── package.json              # Dependencies and scripts
├── .env.example              # Environment variables template
├── README.md                 # This file
├── routes/
│   └── testRoutes.js         # API route definitions
├── services/
│   ├── gemini.js             # Gemini AI service
│   └── playwrightGenerator.js # Playwright test generation
└── tests/                    # Generated test files (auto-created)
    └── *.spec.js            # Generated Playwright tests
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Your Google Gemini API key | Required |
| `GEMINI_MODEL` | Gemini model to use | `gemini-1.5-flash` |
| `PORT` | Server port | `3000` |

### Development

#### Running in Development Mode

```bash
npm run dev
```

This uses nodemon for automatic server restarts on file changes.

#### Testing the API

You can test the API using curl, Postman, or any HTTP client:

```bash
# Health check
curl http://localhost:3000/health

# Generate test
curl -X POST http://localhost:3000/api/generate-test \
  -H "Content-Type: application/json" \
  -d '{"instruction": "Go to google.com and search for Node.js"}'

# List generated tests
curl http://localhost:3000/api/tests
```

### Example Instructions

Here are some example instructions you can try:

- "Go to google.com, search for 'playwright automation', and click on the first result"
- "Navigate to github.com, search for 'fastify', and open the first repository"
- "Go to amazon.in, search for 'laptop', filter by price range 50000-100000, and click on the first product"
- "Visit stackoverflow.com, search for 'javascript async await', and click on the most voted answer"

### Error Handling

The service includes comprehensive error handling:

- **Validation Errors**: Invalid input parameters
- **Gemini API Errors**: API key issues, rate limits, model errors
- **File System Errors**: Permission issues, disk space
- **Playwright Errors**: Test execution failures

All errors are logged and returned with appropriate HTTP status codes.

### Troubleshooting

#### Common Issues

1. **"GEMINI_API_KEY is required"**
   - Make sure you've created a `.env` file with your API key
   - Verify the API key is valid and has proper permissions

2. **"Services not properly initialized"**
   - Check your environment variables
   - Ensure all dependencies are installed

3. **Test execution fails**
   - Make sure Playwright is properly installed
   - Check that the generated code is valid JavaScript
   - Verify network connectivity for web tests

4. **Port already in use**
   - Change the PORT in your `.env` file
   - Or kill the process using the port

#### Getting Help

- Check the server logs for detailed error messages
- Use the `/api/health` endpoint to verify service status
- Ensure your Gemini API key has sufficient quota

### License

MIT License - feel free to use this project for your automation needs!
