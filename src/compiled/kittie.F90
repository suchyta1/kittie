module kittie
	use kittie_internal

	implicit none


    interface kittie_put
        module procedure kittie_put_real_8_1
        module procedure kittie_put_real_8_2
        module procedure kittie_put_real_8_3
        module procedure kittie_put_real_8_4
        module procedure kittie_put_real_4_2
        module procedure kittie_put_complex_8_6
        module procedure kittie_put_real_8_6
        module procedure kittie_put_integer
        module procedure kittie_put_real_8
    end interface kittie_put


    interface kittie_get_selection
        module procedure kittie_get_selection_integer_1
        module procedure kittie_get_selection_real_8_1
        module procedure kittie_get_selection_real_8_2
        module procedure kittie_get_selection_real_8_4
        module procedure kittie_get_selection_complex_8_6
        module procedure kittie_get_selection_real_8_6
    end interface kittie_get_selection


    interface kittie_get
        module procedure kittie_get_integer
        module procedure kittie_get_real_8
    end interface kittie_get


	type coupling_helper
		character(len=:), allocatable :: filename
		type(adios2_engine) :: engine
		type(adios2_io) :: io
		integer :: mode
		integer :: comm
		logical :: usesfile
		logical :: instep=.false.
		logical :: alive=.false.
		character(len=:), allocatable :: engine_type
	end type coupling_helper


	contains

		subroutine until_nonexistent(helper)
			type(coupling_helper), intent(in) :: helper
			logical :: rexists, wexists

			do while (.true.)

				if (helper%mode == adios2_mode_read) then
					inquire(file=trim(helper%filename), exist=rexists)
					if (.not.rexists) then
						cycle
					end if
				end if

				inquire(file=trim(helper%filename)//reading, exist=rexists)
				inquire(file=trim(helper%filename)//writing, exist=wexists)

				if (rexists .and. wexists) then
					if  (helper%mode == adios2_mode_read) then
						call delete_existing(helper%filename//reading)
					end if
					cycle
				else if (rexists .or. wexists) then
					cycle
				else
					exit
				end if

			end do

			if (helper%mode == adios2_mode_write) then
				call touch_file(trim(helper%filename)//writing)
			else if (helper%mode == adios2_mode_read) then
				call touch_file(trim(helper%filename)//reading)
			end if

		end subroutine until_nonexistent


		subroutine lock_logic(helper, yes)
			type(coupling_helper), intent(in) :: helper
			logical, intent(in) :: yes

			if (yes) then
				call until_nonexistent(helper)
			else
				if (helper%mode == adios2_mode_write) then
					call delete_existing(helper%filename//writing)
				else if (helper%mode == adios2_mode_read) then
					call delete_existing(helper%filename//reading)
				end if
			end if

		end subroutine lock_logic


		subroutine lock_state(helper, yes)
			type(coupling_helper), intent(in) :: helper
			logical, intent(in) :: yes
			integer :: ierr, rank, stat

			if (use_mpi .and. (.not. yes))  then
				call mpi_barrier(helper%comm, ierr)
			end if

			if (use_mpi) then
				call mpi_comm_rank(helper%comm, rank, ierr)
			endif

			if ((.not.use_mpi) .or. (rank == 0)) then
				call lock_logic(helper, yes)
			end if

			if (use_mpi .and. yes) then
				call mpi_barrier(helper%comm, ierr)
			end if

		end subroutine lock_state


		subroutine kittie_couple_end_step(helper, ierr, time, lock_print)
			type(coupling_helper), intent(inout) :: helper
			integer, intent(out) :: ierr
			logical, intent(in), optional :: time, lock_print

			if (helper%usesfile) then
				call lock_state(helper, .true.)
			end if

			call adios2_end_step(helper%engine, ierr)
			helper%instep = .false.

			if (helper%usesfile) then
				call lock_state(helper, .false.)

				if (helper%mode == adios2_mode_read) then
					call adios2_close(helper%engine, ierr)
					call adios2_remove_all_variables(helper%io, ierr)
				end if
			end if

		end subroutine kittie_couple_end_step


		function which_engine(io) result(res)
			type(adios2_io), intent(in) :: io
			integer :: ierr
			character(:), allocatable :: res

			res = capitalize(io%engine_type)
		end function which_engine


		function uses_files(engine_type) result(res)
			character(len=*), intent(in) :: engine_type
			integer :: ierr
			logical :: res

			if ((trim(engine_type) == 'BPFILE') .or. (trim(engine_type) == 'BP') .or. (trim(engine_type) == 'HDF5')) then
				res = .true.
			else
				res = .false.
			end if
		end function uses_files


		recursive subroutine file_seek(helper, step)
			type(coupling_helper), intent(inout) :: helper
			integer, intent(in) :: step
			integer :: ierr, i
			integer(kind=8) :: current_step
			logical :: found

			found = .false.
			current_step = -1
			call lock_state(helper, .true.)

#			ifdef USE_MPI
				call adios2_open(helper%engine, helper%io, helper%filename, helper%mode, helper%comm, ierr)
#			else
				call adios2_open(helper%engine, helper%io, helper%filename, helper%mode, ierr)
#			endif


			do while (.true.)
				call adios2_begin_step(helper%engine, adios2_step_mode_next_available, ierr)

				if (ierr == 0) then
					current_step = current_step + 1
				else
					exit
				end if

				if (current_step == step) then
					found = .true.
					exit
				end if

				call adios2_end_step(helper%engine, ierr)
			end do

			call lock_state(helper, .false.)
			if (.not.found) then
				call adios2_close(helper%engine, ierr)
				call adios2_remove_all_variables(helper%io, ierr)
				call file_seek(helper, step)
			end if

		end subroutine file_seek


		subroutine kittie_couple_open(helper)
			type(coupling_helper), intent(inout) :: helper
			integer :: ierr

			if (helper%usesfile) then
				call lock_state(helper, .true.)
			end if

#			ifdef USE_MPI
				call adios2_open(helper%engine, helper%io, helper%filename, helper%mode, helper%comm, ierr)
#			else
				call adios2_open(helper%engine, helper%io, helper%filename, helper%mode, ierr)
#			endif

			if (helper%usesfile) then
				call lock_state(helper, .false.)
			end if
		end subroutine kittie_couple_open


		!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
		! Start of new things that I'm adding
		!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

#		ifdef USE_MPI

			subroutine kittie_initialize(comm, ierr, xml)
				! Intialize Kittie's ADIOS-2 namespace
				integer, intent(in)  :: comm
				integer, intent(out) :: ierr
				character(len=*), intent(in), optional :: xml


				character(len=512) :: eng
				type(adios2_io) :: io


				if (present(xml)) then
					call adios2_init(kittie_adios, trim(xml), comm, adios2_debug_mode_on, ierr)
				else
					call adios2_init(kittie_adios, comm, adios2_debug_mode_on, ierr)
				end if
			end subroutine kittie_initialize

#		else

			subroutine kittie_initialize(ierr, xml)
				! Intialize Kittie's ADIOS-2 namespace
				integer, intent(out) :: ierr
				character(len=*), intent(in), optional :: xmll
				if (present(xml)) then
					call adios2_init(kittie_adios, trim(xml), adios2_debug_mode_on, ierr)
				else
					call adios2_init(kittie_adios, adios2_debug_mode_on, ierr)
				end if
			end subroutine kittie_initialize

#		endif


		subroutine kittie_declare_io(groupname, ierr)
			! Initialize a new Kittie coupling I/O group

			character(len=*), intent(in) :: groupname
			integer, intent(out) :: ierr
			type(adios2_io) :: io

			call adios2_declare_io(io, kittie_adios, trim(groupname), ierr)
			!call adios2_set_engine(io, "SST", ierr)
		end subroutine kittie_declare_io


		subroutine kittie_define_variable(groupname, varname, dtype, ndims, global_dims, global_offsets, local_dims, ierr, constant_dims)
			! At least for now, it makes sense to basically use the ADIOS-2 API

			character(len=*), intent(in) :: groupname
			character(len=*), intent(in) :: varname
			integer, intent(in)  :: dtype
			integer, intent(in)  :: ndims
			integer(kind=8), dimension(:), intent(in), optional :: global_dims
			integer(kind=8), dimension(:), intent(in), optional :: global_offsets
			integer(kind=8), dimension(:), intent(in), optional :: local_dims
			integer, intent(out), optional :: ierr
			logical, intent(in), optional :: constant_dims

			integer :: err
			type(adios2_variable) :: varid
			type(adios2_io)       :: io

			call adios2_at_io(io, kittie_adios, trim(groupname), err)
			!call adios2_set_engine(io, "SST", ierr)

			if (present(global_dims)) then
				if (present(constant_dims)) then
					call adios2_define_variable(varid, io, varname, dtype, ndims, global_dims, global_offsets, local_dims, constant_dims, err)
				else
					call adios2_define_variable(varid, io, varname, dtype, ndims, global_dims, global_offsets, local_dims, adios2_constant_dims, err)
				end if
			else
				call adios2_define_variable(varid, io, varname, dtype, err)
			end if

			if (present(ierr)) then
				ierr = err
			end if

		end subroutine kittie_define_variable


		function kittie_inquire_variable(helper, varname, ierr) result(varid)
			type(coupling_helper), intent(in) :: helper
			character(len=*), intent(in) :: varname
			integer, intent(out) :: ierr
			type(adios2_variable) :: varid
			call adios2_inquire_variable(varid, helper%io, varname, ierr)
		end function kittie_inquire_variable


		function kittie_set_selection(helper, varname, ndim, starts, counts, ierr) result(varid)
			type(coupling_helper), intent(in) :: helper
			character(len=*), intent(in) :: varname
			integer, intent(in) :: ndim
			integer(8), dimension(ndim), intent(in) :: starts, counts
			integer, intent(out) :: ierr
			type(adios2_variable) :: varid
			varid = kittie_inquire_variable(helper, varname, ierr)
			call adios2_set_selection(varid, ndim, starts, counts, ierr)
		end function kittie_set_selection


		subroutine kittie_get_selection_integer_1(outdata, helper, varname, ndim, starts, counts, ierr)
			integer, intent(out), dimension(:) :: outdata
			type(coupling_helper), intent(in) :: helper
			character(len=*), intent(in) :: varname
			integer, intent(in) :: ndim
			integer(8), dimension(ndim), intent(in) :: starts, counts
			integer, intent(out) :: ierr
			type(adios2_variable) :: varid
			varid = kittie_set_selection(helper, varname, ndim, starts, counts, ierr)
			call adios2_get(helper%engine, varid, outdata, adios2_mode_deferred, ierr)
		end subroutine kittie_get_selection_integer_1


		subroutine kittie_get_selection_real_8_1(outdata, helper, varname, ndim, starts, counts, ierr)
			real(kind=8), intent(out), dimension(:) :: outdata
			type(coupling_helper), intent(in) :: helper
			character(len=*), intent(in) :: varname
			integer, intent(in) :: ndim
			integer(8), dimension(ndim), intent(in) :: starts, counts
			integer, intent(out) :: ierr
			type(adios2_variable) :: varid
			varid = kittie_set_selection(helper, varname, ndim, starts, counts, ierr)
			call adios2_get(helper%engine, varid, outdata, adios2_mode_deferred, ierr)
		end subroutine kittie_get_selection_real_8_1


		subroutine kittie_get_selection_real_8_2(outdata, helper, varname, ndim, starts, counts, ierr)
			real(kind=8), intent(out), dimension(:, :) :: outdata
			type(coupling_helper), intent(in) :: helper
			character(len=*), intent(in) :: varname
			integer, intent(in) :: ndim
			integer(8), dimension(ndim), intent(in) :: starts, counts
			integer, intent(out) :: ierr
			type(adios2_variable) :: varid
			varid = kittie_set_selection(helper, varname, ndim, starts, counts, ierr)
			call adios2_get(helper%engine, varid, outdata, adios2_mode_deferred, ierr)
		end subroutine kittie_get_selection_real_8_2
		
		
		subroutine kittie_get_selection_real_8_4(outdata, helper, varname, ndim, starts, counts, ierr)
			real(kind=8), intent(out), dimension(:, :, :, :) :: outdata
			type(coupling_helper), intent(in) :: helper
			character(len=*), intent(in) :: varname
			integer, intent(in) :: ndim
			integer(8), dimension(ndim), intent(in) :: starts, counts
			integer, intent(out) :: ierr
			type(adios2_variable) :: varid
			varid = kittie_set_selection(helper, varname, ndim, starts, counts, ierr)
			call adios2_get(helper%engine, varid, outdata, adios2_mode_deferred, ierr)
		end subroutine kittie_get_selection_real_8_4


		subroutine kittie_get_selection_complex_8_6(outdata, helper, varname, ndim, starts, counts, ierr)
			complex(kind=8), intent(out), dimension(:, :, :, :, :, :) :: outdata
			type(coupling_helper), intent(in) :: helper
			character(len=*), intent(in) :: varname
			integer, intent(in) :: ndim
			integer(8), dimension(ndim), intent(in) :: starts, counts
			integer, intent(out) :: ierr
			type(adios2_variable) :: varid
			varid = kittie_set_selection(helper, varname, ndim, starts, counts, ierr)
			call adios2_get(helper%engine, varid, outdata, adios2_mode_deferred, ierr)
		end subroutine kittie_get_selection_complex_8_6


		subroutine kittie_get_selection_real_8_6(outdata, helper, varname, ndim, starts, counts, ierr)
			real(kind=8), intent(out), dimension(:, :, :, :, :, :) :: outdata
			type(coupling_helper), intent(in) :: helper
			character(len=*), intent(in) :: varname
			integer, intent(in) :: ndim
			integer(8), dimension(ndim), intent(in) :: starts, counts
			integer, intent(out) :: ierr
			type(adios2_variable) :: varid
			varid = kittie_set_selection(helper, varname, ndim, starts, counts, ierr)
			call adios2_get(helper%engine, varid, outdata, adios2_mode_deferred, ierr)
		end subroutine kittie_get_selection_real_8_6


		subroutine kittie_get_integer(outdata, helper, varname, ierr)
			integer, intent(out) :: outdata
			type(coupling_helper), intent(in) :: helper
			character(len=*), intent(in) :: varname
			integer, intent(out) :: ierr
			call adios2_get(helper%engine, trim(varname), outdata, adios2_mode_deferred, ierr)
		end subroutine kittie_get_integer
		

		subroutine kittie_get_real_8(outdata, helper, varname, ierr)
			real(8), intent(out) :: outdata
			type(coupling_helper), intent(in) :: helper
			character(len=*), intent(in) :: varname
			integer, intent(out) :: ierr
			call adios2_get(helper%engine, trim(varname), outdata, adios2_mode_deferred, ierr)
		end subroutine kittie_get_real_8


		subroutine kittie_couple_start(helper, filename, groupname, mode, comm, step, ierr, dir)
			! Roughly the idea is push/fetch the given step, without worrying about how to do safely for different types of I/O.
			! In detail, this is something of a combination of adios2_open() and adios2_begin_step() depending what engine type you're using.

			type(coupling_helper), intent(inout) :: helper
			character(len=*), intent(in) :: filename
			character(len=*), intent(in) :: groupname
			integer, intent(in) :: mode
			integer, intent(in),  optional :: comm
			integer, intent(in),  optional :: step
			integer, intent(out), optional :: ierr
			character(len=*), intent(in), optional :: dir
			type(adios2_io) :: io
			type(adios2_engine) :: engine
			integer :: iierr

			call adios2_at_io(io, kittie_adios, trim(groupname), iierr)
			!call adios2_set_engine(io, "SST", iierr)

			if (.not.helper%alive) then
				
				if (present(comm)) then
					helper%comm = comm
				endif

				helper%engine_type = which_engine(io)
				helper%usesfile = uses_files(helper%engine_type)

				helper%mode = mode
				if (present(dir)) then
					helper%filename = string_copy(trim(dir)//"/"//trim(filename))
				else
					helper%filename = string_copy(trim(filename))
				end if
			end if

			if (.not.helper%alive) then
				helper%io = io
			end if


			if (helper%mode == adios2_mode_write) then
				if (.not.helper%alive) then
					call kittie_couple_open(helper)
				end if
				call adios2_begin_step(helper%engine, adios2_step_mode_append, iierr)

			else if (helper%mode == adios2_mode_read) then

				if (helper%usesfile) then
					if (.not.present(step)) then
						write (*, "('If reading from file for coupling, must give what step you want to read from')")
						stop
					end if

					call file_seek(helper, step)
				else
					if (.not.helper%alive) then
						call kittie_couple_open(helper)
					end if
					call adios2_begin_step(helper%engine, adios2_step_mode_next_available, iierr)
				end if

			end if

			helper%alive = .true.
			if (present(ierr)) then
				ierr = iierr
			end if

		end subroutine kittie_couple_start


		subroutine kittie_put_real_8(helper, varname, outdata, ierr)
			type(coupling_helper), intent(in) :: helper
			character(len=*), intent(in) :: varname
			real(8), intent(in) :: outdata
			integer, intent(out) :: ierr
			call adios2_put(helper%engine, varname, outdata, ierr)
		end subroutine kittie_put_real_8


		subroutine kittie_put_integer(helper, varname, outdata, ierr)
			type(coupling_helper), intent(in) :: helper
			character(len=*), intent(in) :: varname
			integer, intent(in) :: outdata
			integer, intent(out) :: ierr
			call adios2_put(helper%engine, varname, outdata, ierr)
		end subroutine kittie_put_integer


		subroutine kittie_put_real_8_1(helper, varname, outdata, ierr)
			type(coupling_helper), intent(in) :: helper
			character(len=*), intent(in) :: varname
			real(kind=8), dimension(:), intent(in) :: outdata
			integer, intent(out) :: ierr
			call adios2_put(helper%engine, varname, outdata, ierr)
		end subroutine kittie_put_real_8_1


		subroutine kittie_put_real_8_2(helper, varname, outdata, ierr)
			type(coupling_helper), intent(in) :: helper
			character(len=*), intent(in) :: varname
			real(kind=8), dimension(:, :), intent(in) :: outdata
			integer, intent(out) :: ierr
			call adios2_put(helper%engine, varname, outdata, ierr)
		end subroutine kittie_put_real_8_2


		subroutine kittie_put_real_8_3(helper, varname, outdata, ierr)
			type(coupling_helper), intent(in) :: helper
			character(len=*), intent(in) :: varname
			real(kind=8), dimension(:, :, :), intent(in) :: outdata
			integer, intent(out) :: ierr
			call adios2_put(helper%engine, varname, outdata, ierr)
		end subroutine kittie_put_real_8_3


		subroutine kittie_put_real_8_4(helper, varname, outdata, ierr)
			type(coupling_helper), intent(in) :: helper
			character(len=*), intent(in) :: varname
			real(kind=8), dimension(:, :, :, :), intent(in) :: outdata
			integer, intent(out) :: ierr
			call adios2_put(helper%engine, varname, outdata, ierr)
		end subroutine kittie_put_real_8_4


		subroutine kittie_put_real_4_2(helper, varname, outdata, ierr)
			type(coupling_helper), intent(in) :: helper
			character(len=*), intent(in) :: varname
			real(kind=4), dimension(:, :), intent(in) :: outdata
			integer, intent(out) :: ierr
			call adios2_put(helper%engine, varname, outdata, ierr)
		end subroutine kittie_put_real_4_2


		subroutine kittie_put_complex_8_6(helper, varname, outdata, ierr)
			type(coupling_helper), intent(in) :: helper
			character(len=*), intent(in) :: varname
			complex(kind=8), dimension(:, :, :, :, :, :), intent(in) :: outdata
			integer, intent(out) :: ierr
			call adios2_put(helper%engine, varname, outdata, ierr)
		end subroutine kittie_put_complex_8_6

		subroutine kittie_put_real_8_6(helper, varname, outdata, ierr)
			type(coupling_helper), intent(in) :: helper
			character(len=*), intent(in) :: varname
			real(kind=8), dimension(:, :, :, :, :, :), intent(in) :: outdata
			integer, intent(out) :: ierr
			call adios2_put(helper%engine, varname, outdata, ierr)
		end subroutine kittie_put_real_8_6

end module kittie

