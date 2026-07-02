# R/pipeline.R

library(Luminescence)

# Version1: upload data
# ---------------------------
# 1. load_bin_data() : BIN/RDA/RData 등 파일을 읽어서 Risoe.BINfileData 객체를 반환
# 2. inspect_positions() : load_bin_data()를 통해 불러온 객체의 POSITION 정보를 요약
# ---------------------------

load_bin_data <- function(path) {
  # ------------------------------------------------------------
  # 1. path 입력 검증
  # ------------------------------------------------------------
  if (missing(path) || is.null(path) || length(path) != 1 || !nzchar(path)) {
    stop("파일 경로가 비어 있거나 올바르지 않습니다.")
  }

  path <- as.character(path)

  # ------------------------------------------------------------
  # 2. 파일 존재 여부 검증
  # ------------------------------------------------------------
  if (!file.exists(path)) {
    stop(paste0("파일을 찾을 수 없습니다: ", path))
  }

  # ------------------------------------------------------------
  # 3. 경로 정규화
  #    - Python/Streamlit/SQL/JSON 저장 시 경로 일관성 확보
  # ------------------------------------------------------------
  normalized_path <- normalizePath(
    path,
    winslash = "/",
    mustWork = TRUE
  )

  file_name <- basename(normalized_path)
  ext <- tolower(tools::file_ext(normalized_path))

  # ------------------------------------------------------------
  # 4. 확장자 검증
  # ------------------------------------------------------------
  supported_ext <- c("bin", "rda", "rdata")

  if (!(ext %in% supported_ext)) {
    stop(
      paste0(
        "지원하지 않는 파일 형식입니다: ",
        ext,
        " / 지원 형식: ",
        paste(supported_ext, collapse = ", ")
      )
    )
  }

  object_name <- NA_character_
  bin_data <- NULL

  # ------------------------------------------------------------
  # 5. BIN 파일 로딩
  # ------------------------------------------------------------
  if (ext == "bin") {
    bin_data <- read_BIN2R(
      file = normalized_path,
      verbose = FALSE
    )

    object_name <- "read_BIN2R_result"
  }

  # ------------------------------------------------------------
  # 6. RDA/RData 파일 로딩
  #    - 별도 environment에 load해서 현재 환경 오염 방지
  # ------------------------------------------------------------
  else if (ext %in% c("rda", "rdata")) {
    load_env <- new.env(parent = emptyenv())

    loaded_names <- load(
      file = normalized_path,
      envir = load_env
    )

    if (length(loaded_names) == 0) {
      stop("RDA/RData 파일 안에 로드된 객체가 없습니다.")
    }

    candidates <- loaded_names[
      sapply(loaded_names, function(name) {
        obj <- get(name, envir = load_env)
        inherits(obj, "Risoe.BINfileData")
      })
    ]

    if (length(candidates) == 0) {
      stop("RDA/RData 파일 안에서 Risoe.BINfileData 객체를 찾지 못했습니다.")
    }

    object_name <- candidates[1]
    bin_data <- get(object_name, envir = load_env)
  }

  # ------------------------------------------------------------
  # 7. 최종 객체 타입 검증
  # ------------------------------------------------------------
  if (!inherits(bin_data, "Risoe.BINfileData")) {
    stop("불러온 객체가 Risoe.BINfileData 형식이 아닙니다.")
  }

  # ------------------------------------------------------------
  # 8. METADATA 검증
  # ------------------------------------------------------------
  if (is.null(bin_data@METADATA)) {
    stop("Risoe.BINfileData 객체에 METADATA 슬롯이 없습니다.")
  }

  if (nrow(bin_data@METADATA) == 0) {
    stop("Risoe.BINfileData 객체의 METADATA가 비어 있습니다.")
  }

  metadata <- bin_data@METADATA
  metadata_columns <- colnames(metadata)

  # ------------------------------------------------------------
  # 9. POSITION 컬럼 검증
  # ------------------------------------------------------------
  if (!"POSITION" %in% metadata_columns) {
    stop("METADATA에서 POSITION 컬럼을 찾지 못했습니다.")
  }

  positions <- sort(unique(metadata$POSITION))
  positions <- positions[!is.na(positions)]

  if (length(positions) == 0) {
    stop("POSITION 정보를 찾지 못했습니다.")
  }

  # ------------------------------------------------------------
  # 10. 기본 record type 요약
  # ------------------------------------------------------------
  record_types <- character(0)

  if ("LTYPE" %in% metadata_columns) {
    record_types <- sort(unique(as.character(metadata$LTYPE)))
    record_types <- record_types[!is.na(record_types)]
  }

  # ------------------------------------------------------------
  # 11. 반환
  # ------------------------------------------------------------
  list(
    bin_data = bin_data,

    file_path = normalized_path,
    file_name = file_name,
    file_type = ext,

    object_name = object_name,

    n_metadata_rows = as.integer(nrow(metadata)),
    metadata_columns = as.character(metadata_columns),

    n_positions = as.integer(length(positions)),
    positions = as.integer(positions),

    record_types = as.character(record_types)
  )
}

inspect_positions <- function(path) {
  loaded <- load_bin_data(path)

  list(
    file = loaded$file_name,
    file_path = loaded$file_path,
    file_type = loaded$file_type,
    object_name = loaded$object_name,

    n_metadata_rows = loaded$n_metadata_rows,
    metadata_columns = loaded$metadata_columns,

    n_positions = loaded$n_positions,
    positions = loaded$positions,

    record_types = loaded$record_types
  )
}