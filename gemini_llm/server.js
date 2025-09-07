const fastify = require('fastify')({ logger: true });
const cors = require('@fastify/cors');
const path = require('path');
require('dotenv').config();

// Import routes
const testRoutes = require('./routes/testRoutes');

// Register CORS
fastify.register(cors, {
  origin: true,
  credentials: true
});

// Register routes
fastify.register(testRoutes, { prefix: '/api' });

// Health check endpoint
fastify.get('/health', async (request, reply) => {
  return { status: 'OK', timestamp: new Date().toISOString() };
});

// Start server
const start = async () => {
  try {
    const port = process.env.PORT || 3000;
    await fastify.listen({ port, host: '0.0.0.0' });
    console.log(`🚀 Server running on http://localhost:${port}`);
    console.log(`📋 Health check: http://localhost:${port}/health`);
    console.log(`🧪 Test generation: POST http://localhost:${port}/api/generate-test`);
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
};

start();
