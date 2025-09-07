const GeminiService = require('../services/gemini');
const PlaywrightGenerator = require('../services/playwrightGenerator');

// Initialize services
let geminiService;
let playwrightGenerator;

try {
  geminiService = new GeminiService();
  playwrightGenerator = new PlaywrightGenerator();
} catch (error) {
  console.error('Failed to initialize services:', error.message);
}

/**
 * Test generation routes
 */
async function testRoutes(fastify, options) {
  
  // POST /api/generate-test - Generate Playwright test from instruction
  fastify.post('/generate-test', {
    schema: {
      description: 'Generate Playwright test code from plain English instruction',
      tags: ['tests'],
      body: {
        type: 'object',
        required: ['instruction'],
        properties: {
          instruction: {
            type: 'string',
            description: 'Plain English instruction for the test',
            minLength: 10,
            maxLength: 1000
          },
          testName: {
            type: 'string',
            description: 'Optional name for the test file',
            maxLength: 100
          },
          executeTest: {
            type: 'boolean',
            description: 'Whether to execute the generated test',
            default: false
          }
        }
      },
      response: {
        200: {
          type: 'object',
          properties: {
            success: { type: 'boolean' },
            playwrightCode: { type: 'string' },
            testFilePath: { type: 'string' },
            executionResult: { type: 'object' },
            validation: { type: 'object' },
            timestamp: { type: 'string' }
          }
        },
        400: {
          type: 'object',
          properties: {
            success: { type: 'boolean' },
            error: { type: 'string' }
          }
        },
        500: {
          type: 'object',
          properties: {
            success: { type: 'boolean' },
            error: { type: 'string' }
          }
        }
      }
    }
  }, async (request, reply) => {
    try {
      const { instruction, testName, executeTest = false } = request.body;

      // Validate services are initialized
      if (!geminiService || !playwrightGenerator) {
        return reply.status(500).send({
          success: false,
          error: 'Services not properly initialized. Check your environment configuration.'
        });
      }

      // Validate instruction
      if (!instruction || instruction.trim().length < 10) {
        return reply.status(400).send({
          success: false,
          error: 'Instruction must be at least 10 characters long'
        });
      }

      console.log(`📝 Generating test for instruction: "${instruction}"`);

      // Generate Playwright code using Gemini
      const playwrightCode = await geminiService.generatePlaywrightTest(instruction);
      
      // Validate generated code
      const validation = await playwrightGenerator.validateCode(playwrightCode);
      
      if (!validation.isValid) {
        return reply.status(400).send({
          success: false,
          error: 'Generated code validation failed',
          validation: validation
        });
      }

      // Save test file
      const testFilePath = await playwrightGenerator.generateTestFile(
        playwrightCode, 
        testName || 'generated-test'
      );

      const response = {
        success: true,
        playwrightCode: playwrightCode,
        testFilePath: testFilePath,
        validation: validation,
        timestamp: new Date().toISOString()
      };

      // Execute test if requested
      if (executeTest) {
        console.log('🚀 Executing generated test...');
        const executionResult = await playwrightGenerator.executeTest(testFilePath);
        response.executionResult = executionResult;
      }

      console.log('✅ Test generation completed successfully');
      return reply.send(response);

    } catch (error) {
      console.error('❌ Test generation failed:', error);
      
      return reply.status(500).send({
        success: false,
        error: error.message || 'Internal server error during test generation'
      });
    }
  });

  // GET /api/tests - List generated test files
  fastify.get('/tests', {
    schema: {
      description: 'Get list of generated test files',
      tags: ['tests'],
      response: {
        200: {
          type: 'object',
          properties: {
            success: { type: 'boolean' },
            testFiles: { type: 'array', items: { type: 'string' } },
            count: { type: 'number' }
          }
        }
      }
    }
  }, async (request, reply) => {
    try {
      if (!playwrightGenerator) {
        return reply.status(500).send({
          success: false,
          error: 'Playwright generator service not initialized'
        });
      }

      const testFiles = await playwrightGenerator.getTestFiles();
      
      return reply.send({
        success: true,
        testFiles: testFiles,
        count: testFiles.length
      });

    } catch (error) {
      console.error('Error listing test files:', error);
      return reply.status(500).send({
        success: false,
        error: 'Failed to list test files'
      });
    }
  });

  // POST /api/execute-test - Execute a specific test file
  fastify.post('/execute-test', {
    schema: {
      description: 'Execute a specific test file',
      tags: ['tests'],
      body: {
        type: 'object',
        required: ['testFileName'],
        properties: {
          testFileName: {
            type: 'string',
            description: 'Name of the test file to execute'
          }
        }
      },
      response: {
        200: {
          type: 'object',
          properties: {
            success: { type: 'boolean' },
            executionResult: { type: 'object' }
          }
        }
      }
    }
  }, async (request, reply) => {
    try {
      const { testFileName } = request.body;

      if (!playwrightGenerator) {
        return reply.status(500).send({
          success: false,
          error: 'Playwright generator service not initialized'
        });
      }

      const testFilePath = require('path').join(
        require('path').dirname(__dirname), 
        'tests', 
        testFileName
      );

      const executionResult = await playwrightGenerator.executeTest(testFilePath);
      
      return reply.send({
        success: true,
        executionResult: executionResult
      });

    } catch (error) {
      console.error('Error executing test:', error);
      return reply.status(500).send({
        success: false,
        error: 'Failed to execute test'
      });
    }
  });

  // GET /api/health - Service health check
  fastify.get('/health', {
    schema: {
      description: 'Check service health and configuration',
      tags: ['health'],
      response: {
        200: {
          type: 'object',
          properties: {
            success: { type: 'boolean' },
            services: { type: 'object' },
            environment: { type: 'object' }
          }
        }
      }
    }
  }, async (request, reply) => {
    const health = {
      success: true,
      services: {
        gemini: !!geminiService,
        playwrightGenerator: !!playwrightGenerator
      },
      environment: {
        hasGeminiApiKey: !!process.env.GEMINI_API_KEY,
        geminiModel: process.env.GEMINI_MODEL || 'gemini-1.5-flash',
        nodeVersion: process.version
      }
    };

    return reply.send(health);
  });
}

module.exports = testRoutes;
