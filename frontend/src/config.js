// Configuración de TTR_ que se cambia a mano.
//
// usarDatosSimulados
//   true  -> la interfaz usa los datos simulados de src/mocks (no necesita backend)
//   false -> la interfaz llama al backend de FastAPI en http://localhost:8000 (proxy /api de Vite)
//
// También se puede definir con la variable VITE_USE_MOCKS en un archivo .env (ver .env.example);
// si existe, tiene prioridad sobre este valor.
export const CONFIG = {
  usarDatosSimulados: false,
}
