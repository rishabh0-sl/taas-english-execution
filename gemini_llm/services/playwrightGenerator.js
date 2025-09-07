const fs = require('fs').promises;
const path = require('path');
const { exec } = require('child_process');
const { promisify } = require('util');

const execAsync = promisify(exec);

class PlaywrightGenerator {
  constructor() {
    this.testsDir = path.join(__dirname, '..', 'tests');
    this.ensureTestsDirectory();
  }

  /**
   * Ensure tests directory exists
   */
  async ensureTestsDirectory() {
    try {
      await fs.access(this.testsDir);
    } catch (error) {
      await fs.mkdir(this.testsDir, { recursive: true });
    }
  }

  /**
   * Generate and save Playwright test file
   * @param {string} playwrightCode - Generated Playwright code
   * @param {string} testName - Name for the test file
   * @returns {Promise<string>} - Path to the saved test file
   */
  async generateTestFile(playwrightCode, testName = 'generated-test') {
    try {
      // Clean test name for filename
      const cleanTestName = testName.replace(/[^a-zA-Z0-9-_]/g, '-').toLowerCase();
      const timestamp = Date.now();
      const fileName = `${cleanTestName}-${timestamp}.spec.js`;
      const filePath = path.join(this.testsDir, fileName);

      // Add header comment to the generated code
      const codeWithHeader = this.addHeaderComment(playwrightCode, testName);
      
      // Write the test file
      await fs.writeFile(filePath, codeWithHeader, 'utf8');
      
      console.log(`✅ Test file saved: ${filePath}`);
      return filePath;
    } catch (error) {
      console.error('Error saving test file:', error);
      throw new Error(`Failed to save test file: ${error.message}`);
    }
  }

  /**
   * Add header comment to generated code
   * @param {string} code - Original code
   * @param {string} testName - Test name
   * @returns {string} - Code with header
   */
  addHeaderComment(code, testName) {
    const header = `/**
 * Generated Playwright Test
 * Test Name: ${testName}
 * Generated at: ${new Date().toISOString()}
 * 
 * This test was automatically generated from a plain English instruction.
 * Run with: npx playwright test ${path.basename(this.testsDir)}/${path.basename(code.split('\n')[0] || 'test.spec.js')}
 */

`;
    return header + code;
  }

  /**
   * Execute the generated Playwright test
   * @param {string} testFilePath - Path to the test file
   * @returns {Promise<Object>} - Test execution result
   */
  async executeTest(testFilePath) {
    try {
      console.log(`🚀 Executing test: ${testFilePath}`);
      
      // Run the specific test file
      const command = `npx playwright test "${testFilePath}" --reporter=json`;
      const { stdout, stderr } = await execAsync(command, {
        cwd: path.dirname(__dirname),
        timeout: 60000 // 60 seconds timeout
      });

      const result = {
        success: true,
        output: stdout,
        error: stderr,
        testFile: testFilePath
      };

      // Try to parse JSON output if available
      try {
        const jsonOutput = JSON.parse(stdout);
        result.testResults = jsonOutput;
      } catch (parseError) {
        // If JSON parsing fails, keep the raw output
        result.rawOutput = stdout;
      }

      console.log('✅ Test execution completed');
      return result;
    } catch (error) {
      console.error('❌ Test execution failed:', error);
      return {
        success: false,
        error: error.message,
        output: error.stdout || '',
        stderr: error.stderr || '',
        testFile: testFilePath
      };
    }
  }

  /**
   * Validate Playwright code syntax
   * @param {string} code - Code to validate
   * @returns {Promise<Object>} - Validation result
   */
  async validateCode(code) {
    const validation = {
      isValid: true,
      errors: [],
      warnings: []
    };

    // Basic syntax checks
    const requiredImports = ['@playwright/test'];
    const hasRequiredImports = requiredImports.some(imp => code.includes(imp));
    
    if (!hasRequiredImports) {
      validation.errors.push('Missing required Playwright imports');
      validation.isValid = false;
    }

    if (!code.includes('test(')) {
      validation.errors.push('Missing test function definition');
      validation.isValid = false;
    }

    if (!code.includes('async')) {
      validation.warnings.push('Consider using async/await for better readability');
    }

    // Check for common issues
    if (code.includes('setTimeout') && !code.includes('page.waitFor')) {
      validation.warnings.push('Consider using page.waitFor() instead of setTimeout for better reliability');
    }

    return validation;
  }

  /**
   * Clean up old test files (optional utility)
   * @param {number} maxAge - Maximum age in milliseconds
   */
  async cleanupOldTests(maxAge = 24 * 60 * 60 * 1000) { // 24 hours default
    try {
      const files = await fs.readdir(this.testsDir);
      const now = Date.now();
      
      for (const file of files) {
        if (file.endsWith('.spec.js')) {
          const filePath = path.join(this.testsDir, file);
          const stats = await fs.stat(filePath);
          
          if (now - stats.mtime.getTime() > maxAge) {
            await fs.unlink(filePath);
            console.log(`🗑️ Cleaned up old test file: ${file}`);
          }
        }
      }
    } catch (error) {
      console.error('Error cleaning up old tests:', error);
    }
  }

  /**
   * Get list of generated test files
   * @returns {Promise<Array>} - List of test files
   */
  async getTestFiles() {
    try {
      const files = await fs.readdir(this.testsDir);
      return files.filter(file => file.endsWith('.spec.js'));
    } catch (error) {
      console.error('Error reading test files:', error);
      return [];
    }
  }
}

module.exports = PlaywrightGenerator;
