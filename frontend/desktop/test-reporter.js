/**
 * Verification test for Step 4: Electron Integration
 * Tests reportZoneBreach, reportLoitering, and reportFaceMatch from intrusion-reporter.js
 */

const { reportZoneBreach, reportLoitering, reportFaceMatch } = require('./intrusion-reporter');

async function runTest() {
  console.log('--- Testing Step 4: Electron Intrusion Reporter ---');

  // Test 1: User requested example payload
  console.log('\n[1] Testing reportZoneBreach with user payload...');
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
  console.log('Result:', zoneResult);

  // Test 2: reportLoitering
  console.log('\n[2] Testing reportLoitering...');
  const loiterResult = await reportLoitering({
    cameraId: 'BOP-03',
    objectType: 'Human',
    objectId: 'Person #19',
    confidence: 0.88,
    duration: 35.2,
    latitude: 34.5622,
    longitude: 76.1345,
    movementAnalysis: 'Subject stationary in zone for 35s',
  });
  console.log('Result:', loiterResult);

  // Test 3: reportFaceMatch
  console.log('\n[3] Testing reportFaceMatch...');
  const faceResult = await reportFaceMatch({
    cameraId: 'BOP-01',
    personName: 'Suspect-A',
    watchlistId: 'WL-0081',
    confidence: 0.95,
    latitude: 34.5580,
    longitude: 76.1290,
    movementAnalysis: 'Positive facial biometric match on border perimeter',
  });
  console.log('Result:', faceResult);

  console.log('\n--- All intrusion reporter tests completed successfully! ---');
}

runTest().catch((err) => {
  console.error('Test failed:', err);
  process.exit(1);
});
