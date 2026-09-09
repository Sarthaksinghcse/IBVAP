const { reportZoneBreach } = require('./intrusion-reporter');

reportZoneBreach({
  cameraId: 'BOP-07',
  objectType: 'Human',
  objectId: 'Test Person',
  confidence: 0.95,
  latitude: 34.5610,
  longitude: 76.1320,
}).then((res) => {
  console.log('\n--- Quick Test Output ---');
  console.log(res);
  console.log('-------------------------\n');
});
