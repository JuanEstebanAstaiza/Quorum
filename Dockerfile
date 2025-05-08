# Dockerfile.db
# Imagen base muy ligera
FROM alpine:latest

# Crea un directorio dentro del contenedor que se mapeará al volumen del host.
# Este paso no es estrictamente necesario si el volumen se crea al montar,
# pero es una buena práctica declararlo.
RUN mkdir -p /database_storage_mountpoint

# Declara el volumen. Los datos reales vivirán en el host en el directorio montado.
VOLUME /database_storage_mountpoint

# Un comando simple para mantener el contenedor corriendo.
# Esto asegura que el servicio definido en docker-compose "exista" y mantenga el volumen.
CMD ["tail", "-f", "/dev/null"]
