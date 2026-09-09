/**
 * Verification test for Step 4 & End-to-End: Electron Intrusion Reporter
 * Tests reportZoneBreach, reportLoitering, and reportFaceMatch matching Supabase 'alerts' table.
 */

const { reportZoneBreach, reportLoitering, reportFaceMatch, isConfigured, ALERTS_TABLE } = require('./intrusion-reporter');

async function runTest() {
  console.log('====================================================');
  console.log('🛡️  SHIELD / IBVAP — Intrusion Reporter Test Suite');
  console.log('Target Table:', ALERTS_TABLE);
  console.log('Supabase Cloud Configured:', isConfigured() ? '✅ YES' : '⚠️  NO (Operating in local mock mode)');
  console.log('====================================================\n');

  // Test 1: User requested Step 4 payload
  console.log('[1] Testing Step 4: reportZoneBreach...');
  const zoneResult = await reportZoneBreach({
    cameraId: 'BOP-07',
    objectType: 'Human',
    objectId: 'Person #42',
    confidence: 0.91,
    distanceFromFence: 2.5,
    latitude: 34.5610,
    longitude: 76.1320,
    movementAnalysis: 'Subject moving toward restricted perimeter',
  });
  console.log('Result:', JSON.stringify(zoneResult, null, 2));

  // Test 2: Quick Test End-to-End Payload from Setup Guide
  console.log('\n[2] Testing Setup Guide End-to-End Payload (ALT-TEST-001)...');
  const e2eResult = await reportZoneBreach({
    id: 'ALT-TEST-001',
    title: 'Test Zone Breach',
    location: 'BOP-07 • Sector Kargil',
    cameraId: 'BOP-07',
    objectType: 'Human',
    objectId: 'Test Intruder',
    confidence: 0.95,
    latitude: 34.5610,
    longitude: 76.1320,
  });
  console.log('Result:', JSON.stringify(e2eResult, null, 2));

  // Test 3: reportLoitering
  console.log('\n[3] Testing reportLoitering...');
  const loiterResult = await reportLoitering({
    cameraId: 'BOP-03',
    objectType: 'Human',
    objectId: 'Person #19',
    confidence: 0.88,
    durationSeconds: 35,
    latitude: 34.5622,
    longitude: 76.1345,
    movementAnalysis: 'Subject stationary in zone for 35s',
  });
  console.log('Result:', JSON.stringify(loiterResult, null, 2));

  // Test 4: reportFaceMatch
  console.log('\n[4] Testing reportFaceMatch...');
  const faceResult = await reportFaceMatch({
    cameraId: 'BOP-01',
    personName: 'Suspect-A',
    objectId: 'Suspect-A (WL-0081)',
    confidence: 0.95,
    latitude: 34.5580,
    longitude: 76.1290,
    movementAnalysis: 'Positive facial biometric match on border perimeter',
  });
  console.log('Result:', JSON.stringify(faceResult, null, 2));

  console.log('\n====================================================');
  console.log('✅ All intrusion reporter tests completed successfully!');
  console.log('====================================================');
}

runTest().catch((err) => {
  console.error('Test failed:', err);
  process.exit(1);
});
