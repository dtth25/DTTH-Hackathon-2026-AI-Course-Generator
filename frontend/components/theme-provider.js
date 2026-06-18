'use client';

import * as React from 'react';
import { CssBaseline, ThemeProvider, createTheme } from '@mui/material';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1f2a60',
      dark: '#111827',
      light: '#e8ecff',
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#0f766e',
      dark: '#115e59',
      light: '#ccfbf1',
      contrastText: '#ffffff',
    },
    success: { main: '#047857', contrastText: '#ffffff' },
    warning: { main: '#b45309', contrastText: '#ffffff' },
    error: { main: '#be123c', contrastText: '#ffffff' },
    background: {
      default: '#f3f5f9',
      paper: '#ffffff',
    },
    text: {
      primary: '#111827',
      secondary: '#4b5563',
    },
    divider: 'rgba(17, 24, 39, 0.12)',
  },
  shape: {
    borderRadius: 14,
  },
  typography: {
    fontFamily: [
      'Inter',
      'Arial',
      'ui-sans-serif',
      'system-ui',
      '-apple-system',
      'BlinkMacSystemFont',
      'Segoe UI',
      'sans-serif',
    ].join(','),
    h1: { fontWeight: 900, letterSpacing: '-0.045em', color: '#111827' },
    h2: { fontWeight: 850, letterSpacing: '-0.035em', color: '#111827' },
    h3: { fontWeight: 820, letterSpacing: '-0.02em', color: '#111827' },
    h4: { fontWeight: 820, color: '#111827' },
    h5: { fontWeight: 820, color: '#111827' },
    h6: { fontWeight: 820, color: '#111827' },
    subtitle1: { color: '#374151' },
    body1: { color: '#1f2937' },
    body2: { color: '#374151' },
    button: { textTransform: 'none', fontWeight: 850, letterSpacing: '-0.01em' },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          WebkitFontSmoothing: 'antialiased',
          MozOsxFontSmoothing: 'grayscale',
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          background: 'rgba(255,255,255,0.88)',
          color: '#111827',
          boxShadow: 'none',
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          border: '1px solid rgba(17, 24, 39, 0.10)',
          boxShadow: '0 18px 55px rgba(17, 24, 39, 0.075)',
          backgroundImage: 'none',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          minHeight: 42,
          boxShadow: 'none',
          transition: 'transform 160ms ease, box-shadow 160ms ease, background 160ms ease, border-color 160ms ease',
          '&:hover': {
            transform: 'translateY(-1px)',
            boxShadow: '0 10px 22px rgba(17, 24, 39, 0.12)',
          },
          '&.Mui-disabled': {
            backgroundColor: '#e5e7eb',
            color: '#6b7280',
            borderColor: '#d1d5db',
          },
        },
        containedPrimary: {
          color: '#ffffff',
          background: 'linear-gradient(180deg, #29377d 0%, #1f2a60 100%)',
          '&:hover': {
            background: 'linear-gradient(180deg, #1f2a60 0%, #151f49 100%)',
          },
        },
        containedSecondary: {
          color: '#ffffff',
          background: 'linear-gradient(180deg, #0f766e 0%, #115e59 100%)',
        },
        outlinedPrimary: {
          color: '#1f2a60',
          borderColor: 'rgba(31, 42, 96, 0.38)',
          backgroundColor: '#ffffff',
          '&:hover': {
            borderColor: '#1f2a60',
            backgroundColor: '#f4f6ff',
          },
        },
        outlinedError: {
          color: '#be123c',
          backgroundColor: '#fff7f8',
        },
        outlinedWarning: {
          color: '#92400e',
          backgroundColor: '#fffbeb',
        },
        outlinedSuccess: {
          color: '#047857',
          backgroundColor: '#f0fdf4',
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          fontWeight: 800,
          borderRadius: 999,
        },
        colorPrimary: {
          backgroundColor: '#e8ecff',
          color: '#1f2a60',
        },
        colorSecondary: {
          backgroundColor: '#ccfbf1',
          color: '#115e59',
        },
        colorSuccess: {
          backgroundColor: '#dcfce7',
          color: '#166534',
        },
        colorWarning: {
          backgroundColor: '#fef3c7',
          color: '#92400e',
        },
        colorError: {
          backgroundColor: '#ffe4e6',
          color: '#9f1239',
        },
      },
    },
    MuiTabs: {
      styleOverrides: {
        root: {
          minHeight: 48,
          borderBottom: '1px solid rgba(17,24,39,0.10)',
        },
        indicator: {
          height: 3,
          borderRadius: 999,
          backgroundColor: '#1f2a60',
        },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          color: '#4b5563',
          fontWeight: 800,
          '&.Mui-selected': {
            color: '#1f2a60',
          },
        },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: {
          borderRadius: 14,
          border: '1px solid rgba(17,24,39,0.08)',
        },
        standardInfo: {
          backgroundColor: '#eff6ff',
          color: '#1e3a8a',
        },
        standardSuccess: {
          backgroundColor: '#ecfdf5',
          color: '#065f46',
        },
        standardWarning: {
          backgroundColor: '#fffbeb',
          color: '#92400e',
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          height: 9,
          borderRadius: 999,
          backgroundColor: '#e5e7eb',
        },
        bar: {
          borderRadius: 999,
          backgroundColor: '#1f2a60',
        },
      },
    },
  },
});

export default function AppThemeProvider({ children }) {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      {children}
    </ThemeProvider>
  );
}
