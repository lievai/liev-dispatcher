from waitress import serve
import dispatcher as dispatcher

serve(dispatcher.app, host='0.0.0.0', port=5000, threads=600, connection_limit=500)

