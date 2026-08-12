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
          // Same blue as --bluevue-primary, so a Vuetify button and the Blue* control beside it
          // are picked out in one colour.
          primary: '#0A4B6B',
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
