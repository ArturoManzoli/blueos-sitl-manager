import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'

import { createVuetify } from 'vuetify'

// Dark theme tuned to sit comfortably inside the BlueOS interface.
export default createVuetify({
  theme: {
    defaultTheme: 'blueosDark',
    themes: {
      blueosDark: {
        dark: true,
        colors: {
          primary: '#08C',
          secondary: '#26A69A',
          surface: '#1E1E1E',
          background: '#121212',
          error: '#CF6679',
          success: '#4CAF50',
          warning: '#FB8C00',
        },
      },
    },
  },
})
