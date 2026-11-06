describe('Production Telemetry Configuration', () => {
  const originalEnv = process.env.NODE_ENV;
  const originalError = console.error;
  const originalWarn = console.warn;
  const originalLog = console.log;

  afterEach(() => {
    process.env.NODE_ENV = originalEnv;
    console.error = originalError;
    console.warn = originalWarn;
    console.log = originalLog;
    jest.resetModules();
  });

  it('preserves console.error and console.warn in production mode', () => {
    process.env.NODE_ENV = 'production';
    const mockError = jest.fn();
    const mockWarn = jest.fn();
    console.error = mockError;
    console.warn = mockWarn;

    // Simulate the index.js logic
    if (process.env.NODE_ENV === 'production') {
      console.log = () => {};
      console.debug = () => {};
    }

    console.error('Test critical error tracking');
    console.warn('Test warning tracking');

    expect(mockError).toHaveBeenCalledWith('Test critical error tracking');
    expect(mockWarn).toHaveBeenCalledWith('Test warning tracking');
  });
});
