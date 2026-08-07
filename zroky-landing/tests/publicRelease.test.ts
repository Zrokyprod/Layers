import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = resolve(import.meta.dirname, '..');

describe('public release routes', () => {
  it('serves the product page and sends authentication to the dashboard', () => {
    const config = JSON.parse(readFileSync(resolve(root, 'vercel.json'), 'utf8')) as {
      redirects: Array<{ destination: string; source: string }>;
      rewrites: Array<{ destination: string; source: string }>;
    };

    expect(config.rewrites).toContainEqual({ source: '/product', destination: '/index.html' });
    expect(config.redirects.every((redirect) => redirect.destination.startsWith('https://app.zroky.com/'))).toBe(true);
  });

  it('does not publish unsupported loss or action-value figures', () => {
    const pricing = readFileSync(resolve(root, 'src/pages/PricingPage.tsx'), 'utf8');

    expect(pricing).not.toContain('$250K/mo');
    expect(pricing).not.toContain('$8K+');
  });
});
