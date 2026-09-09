const { createClient } = require('@supabase/supabase-js');

const SUPABASE_URL = 'https://euyvbxvbnlmqdppqovix.supabase.co';
const SUPABASE_KEY = 'sb_publishable_NhZFPcp7LgMzDwHF7B_ntA_sN1ugz_G';

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

console.log('Connecting to Supabase Realtime on alerts table...');

let received = false;

const channel = supabase
  .channel('realtime-diagnostic')
  .on(
    'postgres_changes',
    { event: 'INSERT', schema: 'public', table: 'alerts' },
    (payload) => {
      console.log('🎉 REALTIME EVENT RECEIVED IN LISTENER:');
      console.log(payload);
      received = true;
      setTimeout(() => process.exit(0), 500);
    }
  )
  .subscribe(async (status, err) => {
    console.log('Channel subscription status:', status, err ? err : '');

    if (status === 'SUBSCRIBED') {
      console.log('Subscribed! Now inserting test row into alerts table...');
      const testId = `DIAG-${Date.now()}`;
      const { data, error } = await supabase.from('alerts').insert([
        {
          id: testId,
          type: 'ZONE_BREACH',
          severity: 'CRITICAL',
          title: 'Diagnostic Test Alert',
          location: 'BOP-07 • Sector Kargil',
          camera_id: 'BOP-07',
          object_type: 'Human',
          object_id: 'Diagnostic Probe',
          confidence: 0.99,
          created_at: new Date().toISOString(),
        },
      ]);

      if (error) {
        console.error('Insert error:', error);
      } else {
        console.log(`Inserted row ${testId}. Waiting up to 8s for Realtime event...`);
      }

      setTimeout(() => {
        if (!received) {
          console.log('\n❌ TIMEOUT: No Realtime event was received after insert!');
          console.log('DIAGNOSIS: Realtime is either NOT enabled on the "alerts" table, or Row Level Security (RLS) is blocking anon read access.');
          process.exit(1);
        }
      }, 8000);
    }
  });
