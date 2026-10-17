// src/utils/axios.js
import axios from 'axios';

const API_URL = process.env.REACT_APP_API_URL || 'http://127.0.0.1:8000';

const axiosInstance = axios.create({
  baseURL: API_URL,
  withCredentials: true, // 🚀 Ensures cookies are sent with all requests
});

export default axiosInstance;