/**
 * security.js
 * ===========
 * Defensive rendering utilities and XSS protection for Veritas Gate Phase 6 Dashboard.
 * 
 * Rules:
 * - Never inject unescaped user-controlled or proposal text into innerHTML.
 * - Validate addresses and numerical units before display.
 * - Prevent prototype pollution and malicious attribute injection.
 */

export function escapeHTML(value) {
  if (value === null || value === undefined) return '';
  const str = String(value);
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;')
    .replace(/\//g, '&#x2F;');
}

export function sanitizeAddress(address) {
  if (!address || typeof address !== 'string') return '0x0000...0000';
  const clean = address.trim();
  const evmRegex = /^0x[a-fA-F0-9]{40}$/;
  if (!evmRegex.test(clean)) {
    return escapeHTML(clean);
  }
  return clean.toLowerCase();
}

export function truncateAddress(address, prefix = 6, suffix = 4) {
  const clean = sanitizeAddress(address);
  if (clean.length <= prefix + suffix + 2) return clean;
  return `${clean.slice(0, prefix)}...${clean.slice(-suffix)}`;
}

export function formatTokenAmount(rawAmount, decimals = 18, symbol = '') {
  if (rawAmount === null || rawAmount === undefined || rawAmount === '') {
    return { formatted: 'Absent / Missing', exact: 'None', isMissing: true };
  }
  
  // Distinguish missing from zero
  const str = String(rawAmount).trim();
  if (!/^[0-9]+$/.test(str)) {
    return { formatted: escapeHTML(str), exact: str, isMissing: false, isMalformed: true };
  }
  
  const rawBig = BigInt(str);
  if (rawBig === 0n) {
    return { formatted: `0 ${symbol}`.trim(), exact: '0', isZero: true, isMissing: false };
  }

  const divisor = 10n ** BigInt(decimals);
  const integerPart = rawBig / divisor;
  const remainder = rawBig % divisor;
  
  let formatted = integerPart.toLocaleString('en-US');
  if (remainder > 0n) {
    const remStr = remainder.toString().padStart(decimals, '0').slice(0, 4).replace(/0+$/, '');
    if (remStr.length > 0) {
      formatted += `.${remStr}`;
    }
  }
  if (symbol) formatted += ` ${symbol}`;

  return {
    formatted,
    exact: str,
    isMissing: false,
    isZero: false
  };
}

export function safeSetText(element, text) {
  if (element) {
    element.textContent = text ?? '';
  }
}
