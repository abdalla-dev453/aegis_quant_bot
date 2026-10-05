import React from "react";
import ReactDom from "react-dom/client";
import { HelmetProvider } from "react-helmet-async";
import './index.css'
import App from './App.jsx'
import Terminal from './pages/Terminal'
import { Router, Route, Switch } from "wouter";

ReactDom.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <HelmetProvider>
      <Router base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
        <Switch>
          <Route path="/terminal">
            <div className="min-h-screen bg-[#090A0F] text-[#F8FAFC] antialiased">
              <Terminal />
            </div>
          </Route>
          <Route><App /></Route>
        </Switch>
      </Router>
    </HelmetProvider>
  </React.StrictMode>,
)
