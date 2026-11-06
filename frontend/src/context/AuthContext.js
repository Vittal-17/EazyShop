// src/context/AuthContext.js
import { createContext, useEffect, useState, useRef } from 'react';
import axiosInstance from '../utils/axios';
import toast from 'react-hot-toast';
import { useNavigate } from 'react-router-dom';

export const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const navigate = useNavigate();
  const sessionVersion = useRef(0);

  useEffect(() => {
    // Remove credentials left by older clients. JWTs now live only in HttpOnly cookies.
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    return axiosInstance.setSessionExpiredHandler(() => {
      sessionVersion.current += 1;
      setLoading(false);
      localStorage.removeItem('user');
      setUser(null);
      toast.error('Session expired. Please log in again.');
      navigate('/login');
    });
  }, [navigate]);

  // 🚀 HELPER: Fetch absolute latest user profile from backend database
  const refreshUser = async () => {
    const version = sessionVersion.current;
    try {
      const storedUser = localStorage.getItem('user');
      if (storedUser) {
        const parsedUser = JSON.parse(storedUser);
        if (parsedUser && parsedUser.id) {
          const response = await axiosInstance.get(`/api/users/${parsedUser.id}/`);
          if (version !== sessionVersion.current) return null;
          setUser(response.data);
          localStorage.setItem('user', JSON.stringify(response.data));
          return response.data;
        }
      }
    } catch (err) {
      console.error('Failed to refresh user profile:', err);
    }
    return null;
  };

  // 2. HYDRATION & PRODUCTION FRESHNESS CHECK ON MOUNT
  useEffect(() => {
    const initializeAuth = async () => {
      const version = sessionVersion.current;
      const storedUser = localStorage.getItem('user');

      if (storedUser) {
        try {
          const parsedUser = JSON.parse(storedUser);
          setUser(parsedUser);

          // Always fetch fresh data on mount to prevent production caching desync
          if (parsedUser && parsedUser.id) {
            const response = await axiosInstance.get(`/api/users/${parsedUser.id}/`);
            if (version !== sessionVersion.current) return;
            setUser(response.data);
            localStorage.setItem('user', JSON.stringify(response.data));
          }
        } catch (error) {
          if (version !== sessionVersion.current) return;
          console.error('Session initialization error:', error);
          if (error.response?.status === 401) localStorage.removeItem('user');
          setUser(null);
        }
      }
      setLoading(false);
    };

    initializeAuth();
  }, []);

  // 3. LOGIN USER METHOD
  const loginUser = async (email, password) => {
    const version = ++sessionVersion.current;
    try {
      const res = await axiosInstance.post('/api/token/', { email, password });

      if (res.status === 200) {
        // Confirm the browser accepted its HttpOnly session cookies before reporting success.
        const profile = await axiosInstance.get(`/api/users/${res.data.user.id}/`);
        if (version !== sessionVersion.current) return false;
        const userData = profile.data;

        localStorage.setItem('user', JSON.stringify(userData));
        setUser(userData);
        setLoading(false);

        // Guest cart sync algorithm
        const tempCart = JSON.parse(localStorage.getItem('tempCart')) || [];

        if (tempCart.length > 0) {
          toast('Syncing your guest cart...', { icon: '🔄' });

          for (const item of tempCart) {
            try {
              await axiosInstance.post('/api/cart-items/', {
                product: item.product,
                quantity: item.quantity,
              });
            } catch (err) {
              console.error(`Failed to sync product ${item.product}`, err);
            }
          }

          localStorage.removeItem('tempCart');
          toast.success('✨ Cart synced successfully!');
        }

        return true;
      }
    } catch (err) {
      console.error('Login failed:', err.response?.data || err.message);
    }
    return false;
  };

  // 4. CROSS-TAB WALLET SYNC (BroadcastChannel)
  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return;
    const channel = new BroadcastChannel('eazyshop_wallet_sync');
    channel.onmessage = (event) => {
      if (event.data?.type === 'SYNC_WALLET') {
        setUser((prevUser) => {
          if (prevUser && prevUser.id === event.data.userId) {
            const updatedUser = { ...prevUser, wallet_balance: event.data.newBalance };
            localStorage.setItem('user', JSON.stringify(updatedUser));
            return updatedUser;
          }
          return prevUser;
        });
      }
    };
    return () => channel.close();
  }, []);

  const syncWalletBalance = (userId, newBalance) => {
    setUser((prev) => {
      const updatedUser = prev ? { ...prev, wallet_balance: newBalance } : prev;
      if (updatedUser) localStorage.setItem('user', JSON.stringify(updatedUser));
      return updatedUser;
    });
    if (typeof BroadcastChannel !== 'undefined') {
      try {
        const channel = new BroadcastChannel('eazyshop_wallet_sync');
        channel.postMessage({ type: 'SYNC_WALLET', userId, newBalance });
        channel.close();
      } catch (e) {
        console.warn('BroadcastChannel sync failed:', e);
      }
    }
  };

  // 5. LOGOUT USER METHOD
  const logoutUser = async () => {
    try {
      await axiosInstance.logout();
      sessionVersion.current += 1;
      setLoading(false);
      setUser(null);
      localStorage.removeItem('user');
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      navigate('/login');
      return true;
    } catch (err) {
      toast.error('Logout failed. Please retry.');
      return false;
    }
  };

  return (
    <AuthContext.Provider value={{ user, setUser, loginUser, logoutUser, axiosInstance, syncWalletBalance, refreshUser, loading }}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;
