import React from "react";
import ReactDom from "react-dom/client";
import { HelmetProvider } from "react-helmet-async";
import './index.css'
import App from './App.jsx'

ReactDom.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <HelmetProvider>
      <App />
    </HelmetProvider>
  </React.StrictMode>,
)
