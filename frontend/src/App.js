import React, { useEffect, Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import './App.css';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';
import ServerWakeup from './components/ServerWakeup';
import Navbar from './components/Navbar';
import AppToaster from './components/AppToaster';
import ErrorBoundary from './components/ErrorBoundary';
import FullScreenSpinner from './components/FullScreenSpinner';

// Route Code Splitting via React.lazy
const Home = lazy(() => import('./pages/Home'));
const Products = lazy(() => import('./pages/Products'));
const ProductDetails = lazy(() => import('./pages/ProductDetails'));
const Cart = lazy(() => import('./pages/Cart'));
const Checkout = lazy(() => import('./pages/Checkout'));
const GiftCards = lazy(() => import('./pages/GiftCards'));
const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const AdminPanel = lazy(() => import('./pages/AdminPanel'));
const Wishlist = lazy(() => import('./pages/Wishlist'));
const OrderSuccess = lazy(() => import('./pages/OrderSuccess'));
const VendorDashboard = lazy(() => import('./pages/VendorDashboard'));
const ForgotPassword = lazy(() => import('./pages/ForgotPassword'));
const NotFound = lazy(() => import('./pages/NotFound'));

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

      <Suspense fallback={<FullScreenSpinner message="Loading..." />}>
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
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <Router>
        <AuthProvider>
          <AppContent />
        </AuthProvider>
      </Router>
    </ErrorBoundary>
  );
}

export default App;
