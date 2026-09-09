const { createClient } = require('@supabase/supabase-js');
const { reportZoneBreach } = require('./intrusion-reporter');

const SUPABASE_URL = 'https://euyvbxvbnlmqdppqovix.supabase.co';
const SUPABASE_KEY = 'sb_publishable_NhZFPcp7LgMzDwHF7B_ntA_sN1ugz_G';

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

console.log('Connecting to Supabase Realtime channel for alerts table...');

let received = false;

const channel = supabase
  .channel('realtime-diagnostic')
  .on(
    'postgres_changes',
    { event: 'INSERT', schema: 'public', table: 'alerts' },
    (payload) => {
      console.log('\n🎉 REALTIME EVENT RECEIVED IN WEBSOCKET LISTENER!');
      console.log('Event payload:');
      console.log(JSON.stringify(payload, null, 2));
      received = true;
      setTimeout(() => process.exit(0), 500);
    }
  )
  .subscribe(async (status, err) => {
    console.log('Channel subscription status:', status, err ? err : '');

    if (status === 'SUBSCRIBED') {
      console.log('✅ WebSocket channel is SUBSCRIBED!');
      console.log('Now inserting an alert via reportZoneBreach...');

      const result = await reportZoneBreach({
        id: `DIAG-LIVE-${Date.now()}`,
        title: 'Diagnostic Live Alert',
        location: 'BOP-07 • Sector Kargil',
        cameraId: 'BOP-07',
        objectType: 'Human',
        objectId: 'Test Target',
        confidence: 0.98,
        latitude: 34.5610,
        longitude: 76.1320,
      });

      console.log('Insert result:', result.success ? '✅ Row inserted into PostgreSQL' : '❌ Failed: ' + JSON.stringify(result));
      console.log('Waiting up to 8s for Realtime event broadcast on WebSocket...');

      setTimeout(() => {
        if (!received) {
          console.log('\n❌ TIMEOUT: No Realtime broadcast was received!');
          console.log('----------------------------------------------------');
          console.log('Root Cause:');
          console.log('1. Realtime replication is NOT enabled on "alerts" table in Supabase, OR');
          console.log('2. Row Level Security (RLS) is blocking the anon role from receiving the change.');
          console.log('----------------------------------------------------');
          process.exit(1);
        }
      }, 8000);
    }
  });
