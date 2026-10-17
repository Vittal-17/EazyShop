import React, { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import './App.css';
import Home from './pages/Home';
import Products from './pages/Products';
import ProductDetails from './pages/ProductDetails';
import Cart from './pages/Cart';
import Checkout from './pages/Checkout';
import GiftCards from './pages/GiftCards';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import AdminPanel from './pages/AdminPanel';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';
import ServerWakeup from './components/ServerWakeup';
import Navbar from './components/Navbar';
import Wishlist from './pages/Wishlist';
import OrderSuccess from './pages/OrderSuccess';
import AppToaster from './components/AppToaster';
import VendorDashboard from './pages/VendorDashboard';
import ForgotPassword from './pages/ForgotPassword'

// --- ScrollToTop Component ---
function ScrollToTop() {
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return null;
}

function AppContent() {
  return (
    <>
      <ScrollToTop />
      <AppToaster />
      <Navbar />
      <ServerWakeup />

      {/* 🚀 Cleaned out AnimatePresence and AnimatedPage so nothing blocks your spinner! */}
      <Routes>
        <Route path="/" element={<Layout />} />
        <Route index element={<Home />} />
        <Route path="/products" element={<Products />} />
        <Route path="/products/:id" element={<ProductDetails />} />
        <Route path="/cart" element={<Cart />} />
        <Route path="/gift-cards" element={<GiftCards />} />
        <Route path="/checkout" element={<Checkout />} />
        <Route path="/order-success/:orderId" element={<OrderSuccess />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/wishlist" element={<Wishlist />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/vendor" element={ <ProtectedRoute><VendorDashboard /></ProtectedRoute> } />
        <Route path="/dashboard" element={ <ProtectedRoute><Dashboard /></ProtectedRoute> } />
        <Route path="/admin" element={ <ProtectedRoute adminOnly><AdminPanel /></ProtectedRoute> } />
      </Routes>
    </>
  );
}

function App() {
  return (
    <Router>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </Router>
  );
}

export default App;