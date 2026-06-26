import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'

import { createVuetify } from 'vuetify'

// Dark theme tuned to sit comfortably inside the BlueOS interface, matching the
// radcam-manager palette so both extensions feel like one product.
export default createVuetify({
  defaults: {
    VBtn: { variant: 'elevated' },
  },
  theme: {
    defaultTheme: 'blueosDark',
    themes: {
      blueosDark: {
        dark: true,
        colors: {
          primary: '#0B5087',
          secondary: '#26A69A',
          surface: '#363636',
          background: '#121212',
          error: '#CF6679',
          success: '#4CAF50',
          warning: '#FB8C00',
        },
      },
    },
  },
})
