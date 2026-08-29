import { useEffect, useRef, useState } from 'react';
import { View, Text, Pressable, Linking, TextInput } from 'react-native';
import { useNavigate } from 'react-router';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { chargingFlowStyles as styles } from '@evflow/ui';
import { ChargingFlowHeader } from './components/ChargingFlowHeader';
import { SpkluSubmissionGate, validateSpkluPayload, type ValidSpkluSelection } from './spkluQrValidation';

export function ScanSpkluScreen() {
  const navigate = useNavigate();
  const [permission, requestPermission] = useCameraPermissions();
  const [scanned, setScanned] = useState(false);
  const [cameraActive, setCameraActive] = useState(true);
  const [torchAvailable, setTorchAvailable] = useState(false);
  const [torchOn, setTorchOn] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [manualEntryOpen, setManualEntryOpen] = useState(false);
  const [manualStationId, setManualStationId] = useState('');
  const [validating, setValidating] = useState(false);
  const navigationTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const submissionGateRef = useRef(new SpkluSubmissionGate());

  const stopCameraAndNavigate = (path: string, state?: { selection: ValidSpkluSelection }) => {
    if (navigationTimerRef.current) {
      clearTimeout(navigationTimerRef.current);
    }

    setTorchOn(false);
    setCameraActive(false);
    navigationTimerRef.current = setTimeout(() => navigate(path, state ? { state } : undefined), 250);
  };

  const submitStationPayload = async (payload: string) => {
    setScanned(true);
    setValidating(true);
    setScanError(null);
    const result = await submissionGateRef.current.submit(payload, validateSpkluPayload);
    if ('ignored' in result) return;
    if (!result.ok) {
      setScanError(result.error);
      setScanned(false);
      setValidating(false);
      return;
    }
    stopCameraAndNavigate('/charging-flow/initialize', { selection: result.value });
  };

  useEffect(() => {
    return () => {
      setTorchOn(false);
      setCameraActive(false);
      if (navigationTimerRef.current) {
        clearTimeout(navigationTimerRef.current);
      }
    };
  }, []);

  if (!permission) {
    return <View />;
  }

  if (!permission.granted) {
    const handlePermissionPress = () => {
      if (permission.canAskAgain) {
        requestPermission();
        return;
      }

      Linking.openSettings().catch(() => undefined);
    };

    return (
      <View style={styles.page}>
        <ChargingFlowHeader title="Scan SPKLU QR Code" onBack={() => stopCameraAndNavigate('/ev-driver/map')} />

        <View style={styles.cameraContainer}>
          <View style={styles.permissionPrompt}>
            <Text style={styles.permissionPromptText}>
              Camera access is required to scan the SPKLU QR code in the native app.
            </Text>
            <Pressable accessibilityRole="button" onPress={handlePermissionPress} style={styles.secondaryPermissionButton}>
              <Text style={styles.secondaryPermissionButtonText}>
                {permission.canAskAgain ? 'Allow Camera Access' : 'Open Camera Settings'}
              </Text>
            </Pressable>
          </View>
        </View>
      </View>
    );
  }

  const handleBarCodeScanned = ({ type, data }: { type: string; data: string }) => {
    void submitStationPayload(data);
  };

  return (
    <View style={styles.page}>
      <ChargingFlowHeader
        title="Scan SPKLU QR Code"
        onBack={() => stopCameraAndNavigate('/ev-driver/map')}
        rightIconName={torchAvailable && cameraActive ? 'flashlight' : undefined}
        rightIconColor={torchOn ? '#01aeb8' : '#191C1D'}
        rightIconSize={22}
        onRightPress={torchAvailable && cameraActive ? () => setTorchOn(current => !current) : undefined}
      />

      <View style={styles.cameraContainer}>
        {cameraActive ? (
          <>
            <CameraView
              onBarcodeScanned={scanned ? undefined : handleBarCodeScanned}
              barcodeScannerSettings={{
                barcodeTypes: ['qr']
              }}
              style={styles.camera}
              facing="back"
              enableTorch={torchAvailable && torchOn}
              onCameraReady={() => setTorchAvailable(true)}
              onMountError={() => {
                setTorchAvailable(false);
                setTorchOn(false);
              }}
            >
              <View style={styles.cameraOverlay}>
                <View style={styles.cameraCutout} />
                <View style={styles.cameraTextContainer}>
                  <Text style={styles.cameraInstructions}>
                    Position the QR code or barcode found on the SPKLU connector inside the frame to initialize payment.
                  </Text>
                  {scanError ? <Text accessibilityLiveRegion="assertive" style={styles.scanErrorText}>{scanError}</Text> : null}
                  <Text accessibilityRole="button" style={styles.manualEntryLink} onPress={() => { setManualEntryOpen((open) => !open); setScanError(null); }}>
                    Can't scan? Enter Station ID manually
                  </Text>
                  {manualEntryOpen ? (
                    <View style={styles.manualEntryPanel}>
                      <TextInput
                        accessibilityLabel="Station ID"
                        autoCapitalize="none"
                        autoCorrect={false}
                        editable={!validating}
                        onChangeText={setManualStationId}
                        onSubmitEditing={() => void submitStationPayload(manualStationId)}
                        placeholder="e.g. pln_spklu-1"
                        placeholderTextColor="#718087"
                        returnKeyType="go"
                        style={styles.manualEntryInput}
                        value={manualStationId}
                      />
                      <Pressable accessibilityRole="button" disabled={validating} onPress={() => void submitStationPayload(manualStationId)} style={styles.manualEntryButton}>
                        <Text style={styles.manualEntryButtonText}>{validating ? 'Checking…' : 'Continue'}</Text>
                      </Pressable>
                    </View>
                  ) : null}
                </View>
              </View>
            </CameraView>
            <View style={styles.cameraNoticeCard}>
              <Text style={{ fontSize: 24, color: '#01e0f0' }}>ⓘ</Text>
              <Text style={styles.cameraNoticeText}>Make sure you have selected the correct plug profile on the previous screen.</Text>
            </View>
          </>
        ) : (
          <View style={[styles.camera, { backgroundColor: '#000' }]} />
        )}
      </View>
    </View>
  );
}
