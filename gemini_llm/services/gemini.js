const { GoogleGenerativeAI } = require('@google/generative-ai');

class GeminiService {
  constructor() {
    this.apiKey = process.env.GEMINI_API_KEY;
    this.modelName = process.env.GEMINI_MODEL || 'gemini-1.5-flash';
    
    if (!this.apiKey) {
      throw new Error('GEMINI_API_KEY is required in environment variables');
    }
    
    this.genAI = new GoogleGenerativeAI(this.apiKey);
    this.model = this.genAI.getGenerativeModel({ model: this.modelName });
  }

  /**
   * Generate Playwright test code from plain English instruction
   * @param {string} instruction - Plain English instruction for the test
   * @returns {Promise<string>} - Generated Playwright test code
   */
  async generatePlaywrightTest(instruction) {
    try {
      const prompt = this.buildPrompt(instruction);
      
      const result = await this.model.generateContent(prompt);
      const response = await result.response;
      const generatedCode = response.text();
      
      // Clean up the response to extract just the code
      return this.extractCodeFromResponse(generatedCode);
    } catch (error) {
      console.error('Gemini API Error:', error);
      throw new Error(`Failed to generate test code: ${error.message}`);
    }
  }

  /**
   * Build the prompt for Gemini API
   * @param {string} instruction - User instruction
   * @returns {string} - Formatted prompt
   */
  buildPrompt(instruction) {
    return `
You are an expert Playwright test automation engineer. Convert the following plain English instruction into a complete, executable Playwright test script.

Instruction: "${instruction}"

Requirements:
1. Generate a complete Playwright test that can be run with "npx playwright test"
2. Use modern Playwright syntax with async/await
3. Include proper imports and test structure
4. Add helpful comments explaining each step
5. Handle common web interactions like navigation, clicking, typing, waiting
6. Include proper error handling and timeouts
7. Use realistic selectors and wait strategies
8. Make the test robust and reliable

Return ONLY the JavaScript code without any markdown formatting, explanations, or additional text. The code should start with imports and end with the test function.

Example structure:
const { test, expect } = require('@playwright/test');

test('user instruction test', async ({ page }) => {
  // Your generated test code here
});
`;
  }

  /**
   * Extract clean code from Gemini response
   * @param {string} response - Raw response from Gemini
   * @returns {string} - Clean JavaScript code
   */
  extractCodeFromResponse(response) {
    // Remove markdown code blocks if present
    let code = response.replace(/```javascript\n?/g, '').replace(/```\n?/g, '');
    
    // Remove any leading/trailing whitespace
    code = code.trim();
    
    // Ensure the code starts with proper imports
    if (!code.includes("require('@playwright/test')") && !code.includes("import")) {
      code = `const { test, expect } = require('@playwright/test');\n\n${code}`;
    }
    
    return code;
  }

  /**
   * Validate the generated code structure
   * @param {string} code - Generated code
   * @returns {boolean} - Whether code is valid
   */
  validateGeneratedCode(code) {
    const requiredElements = [
      'test(',
      'page',
      'async',
      'await'
    ];
    
    return requiredElements.every(element => code.includes(element));
  }
}

module.exports = GeminiService;
