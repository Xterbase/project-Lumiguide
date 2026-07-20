# R/pipeline.R

library(Luminescence)

# ============================================================
# Common: 로드된 파일 캐시
# ============================================================
# load_bin_data()는 inspect_positions / inspect_rlum_records_by_position /
# save_rlum_record_plot 등 모든 진입점의 첫 줄에서 호출된다.
# 캐시가 없으면 record를 하나 클릭할 때마다 BIN 파일 전체를 다시 파싱하므로,
# 실제 크기의 측정 파일에서는 클릭마다 수 초씩 멈춘다.
#
# 캐시 키 = 정규화 경로 + mtime + size
#   → 같은 경로라도 파일 내용이 바뀌면 키가 달라져 자동으로 무효화된다.
#
# Risoe.BINfileData 객체는 메모리를 많이 쓰므로 최근 N개만 유지한다(LRU).

.bin_cache <- new.env(parent = emptyenv())
.BIN_CACHE_MAX_ENTRIES <- 3L

.bin_cache_key <- function(normalized_path) {
  info <- file.info(normalized_path)

  paste(
    normalized_path,
    as.numeric(info$mtime),
    info$size,
    sep = "|"
  )
}

.bin_cache_get <- function(key) {
  if (!exists(key, envir = .bin_cache, inherits = FALSE)) {
    return(NULL)
  }

  entry <- get(key, envir = .bin_cache, inherits = FALSE)

  # LRU 갱신
  entry$last_used <- Sys.time()
  assign(key, entry, envir = .bin_cache)

  entry$value
}

.bin_cache_put <- function(key, value) {
  assign(
    key,
    list(value = value, last_used = Sys.time()),
    envir = .bin_cache
  )

  keys <- ls(.bin_cache, all.names = TRUE)

  if (length(keys) > .BIN_CACHE_MAX_ENTRIES) {
    last_used <- vapply(
      keys,
      function(k) as.numeric(get(k, envir = .bin_cache)$last_used),
      numeric(1)
    )

    n_drop <- length(keys) - .BIN_CACHE_MAX_ENTRIES
    drop_keys <- keys[order(last_used)][seq_len(n_drop)]

    rm(list = drop_keys, envir = .bin_cache)
  }

  invisible(value)
}

clear_bin_cache <- function() {
  rm(
    list = ls(.bin_cache, all.names = TRUE),
    envir = .bin_cache
  )

  invisible(TRUE)
}

# ============================================================
# Common: data loading
# ============================================================
# BIN/RDA/RData 파일을 읽고, 이후 분석 단계에서 공통으로 사용할
# Risoe.BINfileData 객체와 metadata 정보를 반환한다.

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
  # 3-1. 캐시 조회
  #      같은 파일(경로+mtime+size)이면 재파싱하지 않는다.
  # ------------------------------------------------------------
  cache_key <- .bin_cache_key(normalized_path)
  cached <- .bin_cache_get(cache_key)

  if (!is.null(cached)) {
    return(cached)
  }

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

  # rda/RData는 객체를 여러 개 담을 수 있다. 몇 개 중에 뭘 골랐는지를
  # 호출부(UI)까지 올려보내기 위한 값. bin은 객체 하나짜리 형식이라 1로 고정.
  n_candidates <- 1L
  ignored_objects <- character(0)

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

    # 후보가 여러 개면 첫 번째를 쓰되, 여기서 조용히 넘어가면 안 된다.
    # load()가 돌려주는 순서 = 저장 당시 인자 순서라서, 어느 시료가
    # 분석될지가 연구자에게 보이지 않는 요인으로 결정된다.
    # 몇 개 중 뭘 골랐고 뭘 버렸는지를 반환값에 실어 UI에서 경고한다.
    n_candidates <- length(candidates)
    object_name <- candidates[1]
    ignored_objects <- candidates[-1]

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
  # 11. 반환 (캐시에 적재 후 반환)
  # ------------------------------------------------------------
  result <- list(
    bin_data = bin_data,
    metadata = metadata,

    file_path = normalized_path,
    file_name = file_name,
    file_type = ext,

    object_name = object_name,
    n_candidates = as.integer(n_candidates),
    ignored_objects = as.character(ignored_objects),

    n_metadata_rows = as.integer(nrow(metadata)),
    metadata_columns = as.character(metadata_columns),

    n_positions = as.integer(length(positions)),
    positions = as.integer(positions),

    record_types = as.character(record_types)
  )

  .bin_cache_put(cache_key, result)

  result
}

# ============================================================
# Version1: upload & position inspect
# ============================================================
# load_bin_data()로 불러온 데이터에서 전체 POSITION 정보를 요약한다.
# Upload & Inspect 탭에서 파일 구조, metadata, POSITION 목록을 확인하는 데 사용한다.

inspect_positions <- function(path) {
  loaded <- load_bin_data(path)

  list(
    file = loaded$file_name,
    file_path = loaded$file_path,
    file_type = loaded$file_type,
    object_name = loaded$object_name,
    n_candidates = loaded$n_candidates,
    ignored_objects = loaded$ignored_objects,

    n_metadata_rows = loaded$n_metadata_rows,
    metadata_columns = loaded$metadata_columns,

    n_positions = loaded$n_positions,
    positions = loaded$positions,

    record_types = loaded$record_types
  )
}

# Version2: signal analysis
# ---------------------------
# Version1에서 구현한 파일 로딩/position 확인 흐름을 기반으로,
# 사용자가 선택한 POSITION의 RLum record 목록을 확인하고
# 선택한 record의 신호 곡선을 저장/확인하는 단계다.
#
#
# 3. inspect_rlum_records_by_position()
#    - 선택한 POSITION에 해당하는 metadata row와 RLum record 정보를 요약
#    - record_index, LTYPE, DTYPE, RUN, SET, IRR_TIME, NPOINTS 등을 반환
#
# 4. save_rlum_record_plot()
#    - 선택한 POSITION의 특정 record를 plot으로 저장
#    - 연구자가 신호 형태를 확인하고 signal/background integral을 정할 수 있게 함
# ---------------------------
# 선택한 POSITION의 metadata row와 RLum record를 함께 가져오고,
# 둘의 1:1 정렬이 실제로 성립하는지 검증한다.
#
# 배경 (중요):
#   record_index는 "metadata 행 순서 == RLum record 순서"라는 전제로 만들어지고,
#   save_rlum_record_plot()은 그 번호로 obj[record_index]를 그린다.
#   이 전제가 깨지면 사용자가 고른 record와 다른 곡선이 에러 없이 그려진다.
#
#   그리고 이 전제는 실제로 깨질 수 있다.
#   Risoe.BINfileData2RLum.Analysis()는 내부에서 GRAIN 값별로 결과를 만들기 때문에,
#   한 POSITION 안에 GRAIN이 여러 개면 (single-grain 측정)
#   단일 RLum.Analysis가 아니라 "grain별 RLum.Analysis의 list"를 반환한다.
#   그러면 length(obj)는 record 수가 아니라 grain 수가 되어,
#   obj[record_index]는 record가 아니라 grain을 가리키게 된다.
#
# 예전 구현은 이 경우 warning() 후 min()으로 잘라냈는데,
#   - R의 warning()은 Streamlit UI까지 올라오지 않고
#   - 잘라내도 정렬이 복구되는 게 아니라 그냥 틀린 곡선이 그려진다.
# 조용히 틀린 곡선을 보여주느니 명시적으로 막는다.
.load_position_records <- function(path, pos) {
  loaded <- load_bin_data(path)

  bin_data <- loaded$bin_data
  metadata <- loaded$metadata

  pos <- as.integer(pos)

  metadata_index <- which(metadata$POSITION == pos)
  meta_pos <- metadata[metadata_index, , drop = FALSE]

  if (nrow(meta_pos) == 0) {
    stop(paste0("해당 POSITION의 metadata를 찾지 못했습니다: ", pos))
  }

  # ------------------------------------------------------------
  # GRAIN 검증 (정렬이 깨지는 실제 원인)
  # ------------------------------------------------------------
  grains <- unique(meta_pos$GRAIN)
  grains <- grains[!is.na(grains)]

  if (length(grains) > 1) {
    stop(
      paste0(
        "POSITION ", pos, "에 GRAIN이 여러 개 있습니다 (",
        paste(sort(grains), collapse = ", "),
        "). single-grain 측정 파일은 아직 지원하지 않습니다. ",
        "이 상태로는 record 번호와 실제 곡선이 어긋나므로 분석을 중단합니다."
      )
    )
  }

  obj <- Risoe.BINfileData2RLum.Analysis(
    object = bin_data,
    pos = pos
  )

  if (length(obj) == 0) {
    stop(paste0("해당 POSITION의 RLum record를 찾지 못했습니다: ", pos))
  }

  # GRAIN이 하나여도 record 수가 안 맞으면 정렬을 신뢰할 수 없다.
  if (!inherits(obj, "RLum.Analysis") || nrow(meta_pos) != length(obj)) {
    stop(
      paste0(
        "POSITION ", pos, "의 record 정렬이 맞지 않습니다: ",
        "METADATA record ", nrow(meta_pos), "개, ",
        "RLum record ", length(obj), "개. ",
        "record 번호와 실제 곡선이 어긋날 수 있어 분석을 중단합니다."
      )
    )
  }

  list(
    pos = pos,
    obj = obj,
    meta_pos = meta_pos,
    metadata_index = metadata_index
  )
}

inspect_rlum_records_by_position <- function(path, pos) {
  found <- .load_position_records(path, pos)

  pos <- found$pos
  meta_pos <- found$meta_pos
  metadata_index <- found$metadata_index

  n <- nrow(meta_pos)
  record_index <- seq_len(n)

  get_col <- function(df, col, default = NA) {
    if (col %in% colnames(df)) {
      return(df[[col]])
    }

    rep(default, nrow(df))
  }

  record_type <- as.character(get_col(meta_pos, "LTYPE", "UNKNOWN"))
  dtype <- as.character(get_col(meta_pos, "DTYPE", "UNKNOWN"))
  comment <- as.character(get_col(meta_pos, "COMMENT", ""))
  run <- as.integer(get_col(meta_pos, "RUN", NA))
  set <- as.integer(get_col(meta_pos, "SET", NA))
  irr_time <- as.numeric(get_col(meta_pos, "IRR_TIME", NA))
  npoints <- as.integer(get_col(meta_pos, "NPOINTS", NA))
  low <- as.numeric(get_col(meta_pos, "LOW", NA))
  high <- as.numeric(get_col(meta_pos, "HIGH", NA))
  an_temp <- as.numeric(get_col(meta_pos, "AN_TEMP", NA))
  an_time <- as.numeric(get_col(meta_pos, "AN_TIME", NA))
  light_source <- as.character(get_col(meta_pos, "LIGHTSOURCE", ""))

  record_label <- paste0(
    "#", record_index,
    " | ", record_type,
    " | ", dtype,
    " | ", comment,
    " | RUN ", run,
    " | SET ", set,
    " | IRR ", irr_time
  )

  list(
    position = as.integer(pos),
    n_records = as.integer(n),
    record_index = as.integer(record_index),
    metadata_index = as.integer(metadata_index),
    record_type = as.character(record_type),
    dtype = as.character(dtype),
    comment = as.character(comment),
    run = as.integer(run),
    set = as.integer(set),
    irr_time = as.numeric(irr_time),
    npoints = as.integer(npoints),
    low = as.numeric(low),
    high = as.numeric(high),
    an_temp = as.numeric(an_temp),
    an_time = as.numeric(an_time),
    light_source = as.character(light_source),
    record_label = as.character(record_label)
  )
}

save_rlum_record_plot <- function(path, pos, record_index, output_dir) {
  # inspect_rlum_records_by_position()과 같은 정렬 검증을 거친다.
  # record_index는 그 함수가 만든 번호이므로, 같은 전제 위에서만 유효하다.
  found <- .load_position_records(path, pos)

  pos <- found$pos
  obj <- found$obj

  record_index <- as.integer(record_index)

  if (record_index < 1 || record_index > length(obj)) {
    stop(
      paste0(
        "존재하지 않는 record index입니다: ",
        record_index,
        " / 가능한 범위: 1:",
        length(obj)
      )
    )
  }

  if (!dir.exists(output_dir)) {
    dir.create(output_dir, recursive = TRUE)
  }

  output_dir <- normalizePath(
    output_dir,
    winslash = "/",
    mustWork = TRUE
  )

  file_name <- sprintf(
    "position_%03d_record_%03d_rlum.png",
    pos,
    record_index
  )

  file_path <- file.path(output_dir, file_name)

  png(filename = file_path, width = 1200, height = 800, res = 120)

  # macOS 기본 png 디바이스(quartz)는 dev.off() 시점에야 파일을 디스크에 쓴다.
  # 따라서 dev.off()를 on.exit에만 걸어두면, 아직 파일이 없는 상태에서
  # 아래 normalizePath(mustWork = TRUE)가 실패한다.
  # -> 그리기가 끝나면 즉시 닫아서 flush 하고, on.exit은 에러 시 device 누수 방지용으로만 둔다.
  device_id <- dev.cur()
  on.exit(
    if (dev.cur() == device_id) dev.off(),
    add = TRUE
  )

  plot_RLum(obj[record_index])

  dev.off()

  if (!file.exists(file_path)) {
    stop(paste0("Curve 이미지를 생성하지 못했습니다: ", file_path))
  }

  normalized_file_path <- normalizePath(
    file_path,
    winslash = "/",
    mustWork = TRUE
  )

  list(
    position = as.integer(pos),
    record_index = as.integer(record_index),
    plot_file = as.character(normalized_file_path)
  )
}


# ============================================================
# Version3: SAR analysis
# ============================================================
# Signal 단계에서 정한 signal/background integral로 POSITION별 SAR 분석을 돌려
# De 값을 얻는다. 여기서 나온 De 모음이 다음 단계(De 분포 -> CAM/MAM/FMM)의 입력이다.
#
# integral 문자열 파싱
# ---------------------
# signal_tab은 "1:2" 같은 자유 입력 문자열을 저장한다. 이건 신뢰 경계라서
# R로 넘어온 시점에 반드시 검증해야 한다. 검증 실패를 그대로 두면
# analyse_SAR.CWOSL()이 엉뚱한 채널을 적분하고도 에러 없이 De를 뱉는다.
.parse_integral <- function(value, label, n_points) {
  if (is.null(value) || length(value) != 1 || is.na(value) || !nzchar(value)) {
    stop(paste0(label, "이(가) 비어 있습니다. 예: 1:2"))
  }

  parts <- strsplit(trimws(as.character(value)), "[:,-]")[[1]]
  parts <- trimws(parts[nzchar(trimws(parts))])

  if (length(parts) != 2) {
    stop(paste0(label, " 형식이 올바르지 않습니다: '", value, "' / 예: 1:2"))
  }

  nums <- suppressWarnings(as.integer(parts))

  if (any(is.na(nums))) {
    stop(paste0(label, "에 숫자가 아닌 값이 있습니다: '", value, "' / 예: 1:2"))
  }

  if (nums[1] < 1) {
    stop(paste0(label, "의 시작 채널은 1 이상이어야 합니다: ", nums[1]))
  }

  if (nums[1] > nums[2]) {
    stop(
      paste0(
        label, "의 시작이 끝보다 큽니다: ", nums[1], ":", nums[2],
        " / 예: ", nums[2], ":", nums[1]
      )
    )
  }

  if (!is.na(n_points) && nums[2] > n_points) {
    stop(
      paste0(
        label, "이 측정 채널 수를 넘습니다: ", nums[1], ":", nums[2],
        " / 이 파일의 채널 수(NPOINTS): ", n_points
      )
    )
  }

  as.integer(nums)
}


# POSITION 하나에 대해 SAR을 돌리고 필요한 값만 뽑는다.
.run_sar_one <- function(path, pos, signal_integral, background_integral) {
  found <- .load_position_records(path, pos)

  res <- analyse_SAR.CWOSL(
    object = found$obj,
    signal_integral = signal_integral,
    background_integral = background_integral,
    plot = FALSE,
    verbose = FALSE
  )

  if (is.null(res)) {
    stop("SAR 분석이 결과를 반환하지 않았습니다.")
  }

  data <- get_RLum(res, "data")

  if (is.null(data) || nrow(data) == 0) {
    stop("SAR 결과에 De 값이 없습니다.")
  }

  # 품질 지표는 rejection.criteria 표에 Criteria/Value 행으로 들어온다.
  # 기획서가 요구하는 recycling ratio / recuperation을 이름으로 찾아 꺼낸다.
  rc <- try(get_RLum(res, "rejection.criteria"), silent = TRUE)

  pick_rc <- function(pattern) {
    if (inherits(rc, "try-error") || is.null(rc) || nrow(rc) == 0) {
      return(NA_real_)
    }

    hit <- grep(pattern, rc$Criteria, ignore.case = TRUE)

    if (length(hit) == 0) {
      return(NA_real_)
    }

    as.numeric(rc$Value[hit[1]])
  }

  get_one <- function(col) {
    if (col %in% colnames(data)) data[[col]][1] else NA
  }

  list(
    de = as.numeric(get_one("De")),
    de_error = as.numeric(get_one("De.Error")),
    rc_status = as.character(get_one("RC.Status")),
    fit = as.character(get_one("Fit")),
    n_n = as.numeric(get_one("n_N")),
    recycling_ratio = pick_rc("Recycling ratio"),
    recuperation = pick_rc("Recuperation")
  )
}


# 여러 POSITION에 대해 SAR을 일괄 실행한다.
#
# 한 POSITION이 실패해도 전체를 중단하지 않는다.
#   De 분포를 만들려면 aliquot이 여러 개 필요한데, 그 중 하나가 fit 실패나
#   multi-GRAIN으로 막힌다고 나머지 정상 결과까지 버리면 분석이 불가능해진다.
#   실패한 POSITION은 사유와 함께 따로 모아서 UI가 보여줄 수 있게 반환한다.
run_sar_analysis <- function(path, positions, signal_integral, background_integral) {
  loaded <- load_bin_data(path)

  if (is.null(positions) || length(positions) == 0) {
    stop("분석할 POSITION이 선택되지 않았습니다.")
  }

  positions <- sort(unique(as.integer(positions)))

  unknown <- setdiff(positions, loaded$positions)

  if (length(unknown) > 0) {
    stop(
      paste0(
        "파일에 없는 POSITION입니다: ",
        paste(unknown, collapse = ", ")
      )
    )
  }

  metadata <- loaded$metadata

  n_points <- if ("NPOINTS" %in% colnames(metadata)) {
    suppressWarnings(max(as.integer(metadata$NPOINTS), na.rm = TRUE))
  } else {
    NA_integer_
  }

  if (!is.finite(n_points)) {
    n_points <- NA_integer_
  }

  sig <- .parse_integral(signal_integral, "Signal integral", n_points)
  bg <- .parse_integral(background_integral, "Background integral", n_points)

  ok_position <- integer(0)
  ok_de <- numeric(0)
  ok_de_error <- numeric(0)
  ok_rc_status <- character(0)
  ok_fit <- character(0)
  ok_n_n <- numeric(0)
  ok_recycling <- numeric(0)
  ok_recuperation <- numeric(0)

  failed_position <- integer(0)
  failed_reason <- character(0)

  for (pos in positions) {
    one <- try(
      .run_sar_one(path, pos, sig, bg),
      silent = TRUE
    )

    if (inherits(one, "try-error")) {
      failed_position <- c(failed_position, pos)
      failed_reason <- c(
        failed_reason,
        trimws(as.character(attr(one, "condition")$message))
      )
      next
    }

    ok_position <- c(ok_position, pos)
    ok_de <- c(ok_de, one$de)
    ok_de_error <- c(ok_de_error, one$de_error)
    ok_rc_status <- c(ok_rc_status, one$rc_status)
    ok_fit <- c(ok_fit, one$fit)
    ok_n_n <- c(ok_n_n, one$n_n)
    ok_recycling <- c(ok_recycling, one$recycling_ratio)
    ok_recuperation <- c(ok_recuperation, one$recuperation)
  }

  if (length(ok_position) == 0) {
    stop(
      paste0(
        "선택한 POSITION ", length(positions), "개 전부 SAR 분석에 실패했습니다. ",
        "첫 번째 사유: ",
        if (length(failed_reason) > 0) failed_reason[1] else "(사유 없음)"
      )
    )
  }

  list(
    signal_integral = as.integer(sig),
    background_integral = as.integer(bg),

    n_requested = as.integer(length(positions)),
    n_success = as.integer(length(ok_position)),
    n_failed = as.integer(length(failed_position)),

    position = as.integer(ok_position),
    de = as.numeric(ok_de),
    de_error = as.numeric(ok_de_error),
    rc_status = as.character(ok_rc_status),
    fit = as.character(ok_fit),
    n_n = as.numeric(ok_n_n),
    recycling_ratio = as.numeric(ok_recycling),
    recuperation = as.numeric(ok_recuperation),

    failed_position = as.integer(failed_position),
    failed_reason = as.character(failed_reason)
  )
}