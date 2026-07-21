#!/usr/bin/env node
/**
 * Generate TypeScript types from backend OpenAPI spec
 * 
 * Usage:
 *   pnpm generate:api
 * 
 * Configuration (environment variables):
 *   - BACKEND_SPEC_PATH: Path to local openapi.json (default: ../dazah-backend/openapi.json)
 *   - API_BASE_URL: Backend URL to fetch from if local file not found (default: http://localhost:8000)
 * 
 * The script will:
 *   1. Try to read from BACKEND_SPEC_PATH (local file)
 *   2. If not found, fetch from API_BASE_URL/openapi.json
 */

import { execSync } from 'child_process';
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = join(__dirname, '..');
const DEFAULT_BACKEND_SPEC = join(FRONTEND_ROOT, '..', 'dazah-backend', 'openapi.json');
const BACKEND_SPEC = process.env.BACKEND_SPEC_PATH || DEFAULT_BACKEND_SPEC;
const BACKEND_URL = process.env.API_BASE_URL || 'http://localhost:8000';
const OUTPUT_DIR = join(FRONTEND_ROOT, 'src/types/generated');

async function fetchSpec() {
  console.log(`🔄 Fetching OpenAPI spec from ${BACKEND_URL}...`);
  const response = await fetch(`${BACKEND_URL}/openapi.json`);
  if (!response.ok) {
    throw new Error(`Backend returned ${response.status}`);
  }
  return await response.json();
}

async function readLocalSpec() {
  console.log(`🔄 Reading OpenAPI spec from ${BACKEND_SPEC}...`);
  const content = readFileSync(BACKEND_SPEC, 'utf-8');
  return JSON.parse(content);
}

async function main() {
  try {
    let spec;
    
    // Try local file first, then fetch from URL
    if (existsSync(BACKEND_SPEC)) {
      spec = await readLocalSpec();
    } else {
      spec = await fetchSpec();
    }
    
    const specPath = join(OUTPUT_DIR, 'openapi.json');
    
    // Ensure output directory exists
    if (!existsSync(OUTPUT_DIR)) {
      mkdirSync(OUTPUT_DIR, { recursive: true });
    }
    
    // Save spec for reference
    writeFileSync(specPath, JSON.stringify(spec, null, 2));
    console.log(`✓ Saved OpenAPI spec to src/types/generated/openapi.json`);
    
    // Generate TypeScript types
    console.log('🔄 Generating TypeScript types...');
    execSync(`npx openapi-typescript ${specPath} -o ${join(OUTPUT_DIR, 'schema.ts')}`, {
      stdio: 'inherit'
    });
    console.log(`✓ Generated types at src/types/generated/schema.ts`);
    
    console.log('\n✅ Code generation complete!');
    console.log('\nNext steps:');
    console.log('  1. Import types from @/types/generated/schema');
    console.log('  2. Update src/lib/api/*.ts to use generated types');
    console.log('  3. Run: pnpm typecheck');
    
  } catch (error) {
    console.error('❌ Code generation failed:', error.message);
    console.error('\nMake sure either:');
    console.error('  - Local spec exists at:', BACKEND_SPEC);
    console.error('  - Or backend is running at:', BACKEND_URL);
    console.error('\nYou can configure paths via environment variables:');
    console.error('  BACKEND_SPEC_PATH=/path/to/openapi.json pnpm generate:api');
    console.error('  API_BASE_URL=http://backend:8000 pnpm generate:api');
    process.exit(1);
  }
}

main();
