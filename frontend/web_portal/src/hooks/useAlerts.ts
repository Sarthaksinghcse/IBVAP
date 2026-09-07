import { useEffect } from 'react';
import { useStore } from '../store/useStore';
import * as api from '../services/api';
import { MOCK_ALERTS } from '../services/mock/mockData';
import type { AlertStatus } from '../types';

/**
 * Initialises alerts in the store and exposes acknowledge helper.
 */
export function useAlerts() {
  const { alerts, setAlerts, updateAlertStatus } = useStore();
  const isMock = import.meta.env.VITE_USE_MOCK === 'true';

  useEffect(() => {
    if (isMock) {
      setAlerts(MOCK_ALERTS);
      return;
    }

    api
      .getAlerts()
      .then(setAlerts)
      .catch((e) => console.error('[useAlerts]', e));
  }, []);

  const acknowledge = async (id: string) => {
    if (isMock) {
      updateAlertStatus(id, 'ACKNOWLEDGED');
      return;
    }
    try {
      await api.patchAlert(id, 'ACKNOWLEDGED');
      updateAlertStatus(id, 'ACKNOWLEDGED');
    } catch (e) {
      console.error('[useAlerts] acknowledge', e);
    }
  };

  const updateStatus = async (id: string, status: AlertStatus) => {
    if (isMock) {
      updateAlertStatus(id, status);
      return;
    }
    try {
      await api.patchAlert(id, status);
      updateAlertStatus(id, status);
    } catch (e) {
      console.error('[useAlerts] updateStatus', e);
    }
  };

  return { alerts, acknowledge, updateStatus };
}
