import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.sergiostudio.editor',
  appName: 'Sergio Studio',
  webDir: '../src/openjarvis/server/static_local',
  server: {
    androidScheme: 'https',
    cleartext: true,
  },
  ios: {
    contentInset: 'always',
    scheme: 'SergioStudio',
    limitsNavigationsToAppBoundDomains: false,
    scrollEnabled: 'true',
    allowsLinkPreview: false,
    backgroundColor: '#070b11',
  },
  android: {
    backgroundColor: '#070b11',
    allowMixedContent: true,
    captureInput: true,
    webContentsDebuggingEnabled: true,
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 2000,
      launchAutoHide: true,
      backgroundColor: '#070b11',
      androidSplashResourceName: 'splash',
      androidScaleType: 'CENTER_CROP',
      showSpinner: false,
      splashFullScreen: true,
      splashImmersive: true,
    },
    Camera: {
      allowEditing: false,
      resultType: 'uri',
      saveToGallery: false,
      source: 'prompt',
      quality: 95,
    },
    LocalNotifications: {
      smallIcon: 'ic_stat_icon_config_sample',
      iconColor: '#488AFF',
      sound: 'beep.wav',
    },
    PushNotifications: {
      presentationOptions: ['badge', 'sound', 'alert'],
    },
    Filesystem: {
      directory: 'DOCUMENTS',
    },
    Media: {
      ios: {
        backgroundColor: '#070b11',
      },
    },
    Keyboard: {
      resize: 'body',
      style: 'dark',
      resizeOnFullScreen: true,
    },
    StatusBar: {
      style: 'dark',
      backgroundColor: '#070b11',
      overlaysWebView: true,
    },
    App: {
      appUrlOpen: {
        url: 'sergiostudio://',
      },
    },
  },
};

export default config;
