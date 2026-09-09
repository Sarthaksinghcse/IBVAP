const { reportZoneBreach } = require('./intrusion-reporter');

async function main() {
  console.log('🚨 Dispatching Live Test Alert to Supabase Realtime...');
  
  const res = await reportZoneBreach({
    id: `ALERT-${Date.now().toString(36).toUpperCase()}`,
    title: 'CRITICAL PERIMETER BREACH',
    location: 'BOP-07 • Sector Kargil',
    cameraId: 'BOP-07',
    objectType: 'Human',
    objectId: 'Unidentified Intruder',
    confidence: 0.99,
    distanceFromFence: 1.2,
    latitude: 34.5610,
    longitude: 76.1320,
    movementAnalysis: 'Subject sprinting across perimeter fence zone',
  });

  console.log('\n[SUCCESS] Alert broadcasted to Supabase:');
  console.log('Alert ID:', res.data.id);
  console.log('Title:', res.data.title);
  console.log('Location:', res.data.location);
  console.log('Timestamp:', res.data.timestamp);
  console.log('\nIf your Shield iOS app is OPEN on your phone screen, you will see:');
  console.log('1. Siren sound playing 🔊');
  console.log('2. Haptic vibration 📳');
  console.log('3. In-app emergency alert banner 🚨');
}

main().catch(console.error);
